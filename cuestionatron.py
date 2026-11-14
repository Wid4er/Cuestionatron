#!/usr/bin/env python3
"""Cuestionatron: cuestionarios Markdown, servidos solo en el equipo local."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import random
import secrets
import sys
import threading
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
APP_FOLDER = (Path(os.environ['CUESTIONATRON_HOME']).resolve() if os.environ.get('CUESTIONATRON_HOME')
              else Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ROOT)
DEFAULT_QUIZ_FOLDER = APP_FOLDER / 'Cuestionarios'
MAX_BODY = 1_000_000
SESSION_TTL = 6 * 60 * 60


@dataclass(frozen=True)
class Answer:
    text: str
    correct: bool


@dataclass(frozen=True)
class Question:
    text: str
    answers: tuple[Answer, ...]
    line: int


class QuizFormatError(ValueError):
    pass


def parse_quiz(source: str) -> list[Question]:
    """Lee # enunciado y respuestas +/-. No interpreta HTML ni Markdown."""
    questions: list[Question] = []
    title: str | None = None
    answers: list[Answer] = []
    start = 0

    def finish() -> None:
        if title is None:
            return
        if not any(answer.correct for answer in answers):
            raise QuizFormatError(f'Línea {start}: «{title}» necesita una respuesta con +.')
        if not any(not answer.correct for answer in answers):
            raise QuizFormatError(f'Línea {start}: «{title}» necesita una respuesta con -.')
        if len({answer.text.casefold() for answer in answers}) != len(answers):
            raise QuizFormatError(f'Línea {start}: hay respuestas repetidas en «{title}».')
        questions.append(Question(title, tuple(answers), start))

    for line_no, raw in enumerate(source.lstrip('\ufeff').splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#'):
            finish()
            title = line[1:].strip()
            if not title:
                raise QuizFormatError(f'Línea {line_no}: falta el enunciado después de #.')
            answers = []
            start = line_no
        elif line.startswith(('+', '-')):
            if title is None:
                raise QuizFormatError(f'Línea {line_no}: hay una respuesta antes de la primera pregunta.')
            value = line[1:].strip()
            if not value:
                raise QuizFormatError(f'Línea {line_no}: la respuesta está vacía.')
            answers.append(Answer(value, line[0] == '+'))
        else:
            raise QuizFormatError(f'Línea {line_no}: usa # para preguntas y + o - para respuestas.')
    finish()
    if not questions:
        raise QuizFormatError('El archivo no contiene preguntas.')
    return questions


def read_catalog(folder: Path) -> tuple[list[dict], dict[str, list[Question]]]:
    catalog = []
    valid = {}
    folder.mkdir(parents=True, exist_ok=True)
    for path in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
        if path.suffix.lower() != '.md' or not path.is_file() or path.is_symlink():
            continue
        entry = {'id': path.name, 'name': path.stem, 'count': 0, 'multiple': 0, 'error': None}
        try:
            questions = parse_quiz(path.read_text(encoding='utf-8-sig'))
            valid[path.name] = questions
            entry['count'] = len(questions)
            entry['multiple'] = sum(sum(a.correct for a in q.answers) > 1 for q in questions)
        except (OSError, UnicodeError, QuizFormatError) as exc:
            entry['error'] = str(exc)
        catalog.append(entry)
    return catalog, valid


def make_session(bank: dict[str, list[Question]], selected: list[str], count: int,
                 penalty: float, shuffle: bool, rng=None, question_limit: int | None = 20) -> dict:
    rng = rng or random.SystemRandom()
    pool = [(name, question) for name in selected for question in bank[name]]
    if question_limit is not None and question_limit < len(pool):
        # La muestra es aleatoria incluso si después se conserva el orden original.
        positions = sorted(rng.sample(range(len(pool)), question_limit))
        pool = [pool[index] for index in positions]
    questions = []
    for name, question in pool:
        correct = [a for a in question.answers if a.correct]
        incorrect = [a for a in question.answers if not a.correct]
        # Siempre hay al menos una opción incorrecta, incluso con muchos +.
        option_count = max(count, len(correct) + 1)
        options = correct + rng.sample(incorrect, min(len(incorrect), option_count - len(correct)))
        rng.shuffle(options)
        questions.append({
            'id': f'q{len(questions)}', 'source': Path(name).stem, 'text': question.text,
            'multiple': len(correct) > 1,
            'options': [{'id': str(i), 'text': a.text, 'correct': a.correct}
                        for i, a in enumerate(options)],
        })
    if shuffle:
        rng.shuffle(questions)
    return {'created': time.monotonic(), 'penalty': penalty, 'questions': questions}


def public_session(session: dict) -> list[dict]:
    return [{**q, 'options': [{k: v for k, v in a.items() if k != 'correct'}
                             for a in q['options']]} for q in session['questions']]


def grade_session(session: dict, answers: dict) -> dict:
    known = {q['id'] for q in session['questions']}
    if any(key not in known for key in answers):
        raise ValueError('La respuesta contiene una pregunta desconocida.')
    counts = {'correct': 0, 'incorrect': 0, 'blank': 0}
    review = []
    for question in session['questions']:
        selected = answers.get(question['id'], [])
        allowed = {a['id'] for a in question['options']}
        if (not isinstance(selected, list) or any(not isinstance(a, str) or a not in allowed for a in selected)
                or len(set(selected)) != len(selected)):
            raise ValueError('Las opciones enviadas no son válidas.')
        if not question['multiple'] and len(selected) > 1:
            raise ValueError('Esta pregunta solo admite una respuesta.')
        correct = {a['id'] for a in question['options'] if a['correct']}
        status = 'blank' if not selected else ('correct' if set(selected) == correct else 'incorrect')
        counts[status] += 1
        review.append({**question, 'selected': selected, 'status': status})
    total = len(session['questions'])
    net = counts['correct'] - counts['incorrect'] * session['penalty']
    return {**counts, 'total': total, 'net': round(net, 4), 'penalty': session['penalty'],
            'score': round(max(0, min(10, net / total * 10)), 2), 'review': review}


class QuizServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, folder: Path):
        self.folder = folder
        self.sessions: dict[str, dict] = {}
        self.lock = threading.Lock()
        super().__init__(address, partial(QuizHandler, directory=str(ROOT / 'web')))


class QuizHandler(SimpleHTTPRequestHandler):
    server: QuizServer

    def log_message(self, format, *args):
        # pythonw.exe y las aplicaciones sin consola no disponen de stderr.
        if sys.stderr is not None:
            super().log_message(format, *args)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()

    def send_json(self, status: int, data: dict):
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == '/api/catalog':
            try:
                catalog, _ = read_catalog(self.server.folder)
                self.send_json(200, {'quizzes': catalog})
            except OSError:
                self.send_json(500, {'error': 'No se pudo leer la carpeta Cuestionarios.'})
        elif self.path in ('/', '/index.html', '/app.js', '/style.css', '/favicon.svg', '/ganso-bailon.gif', '/celebracion.mp3'):
            super().do_GET()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        # Solo se aceptan peticiones de la propia interfaz local.
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        if origin and origin != f'http://{host}':
            self.send_json(403, {'error': 'Origen no permitido.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > MAX_BODY:
                raise ValueError('El tamaño de la petición no es válido.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('La petición debe ser un objeto JSON.')
            if self.path == '/api/start':
                self.start_session(data)
            elif self.path == '/api/grade':
                self.grade(data)
            else:
                self.send_json(404, {'error': 'Ruta desconocida.'})
        except (ValueError, UnicodeError) as exc:
            self.send_json(400, {'error': str(exc)})
        except OSError:
            self.send_json(500, {'error': 'No se pudo leer la carpeta Cuestionarios.'})

    def start_session(self, data: dict):
        selected = data.get('quizzes')
        if (not isinstance(selected, list) or not selected or
                any(not isinstance(name, str) for name in selected) or len(set(selected)) != len(selected)):
            raise ValueError('Selecciona al menos un cuestionario, sin repetir archivos.')
        count = data.get('answer_count', 4)
        if type(count) is not int or not 2 <= count <= 21:
            raise ValueError('El número de opciones debe estar entre 2 y 21.')
        penalty = data.get('penalty', 0)
        if (type(penalty) not in (float, int) or not math.isfinite(penalty) or not 0 <= penalty <= 10):
            raise ValueError('La penalización debe estar entre 0 y 10.')
        shuffle = data.get('shuffle', True)
        if type(shuffle) is not bool:
            raise ValueError('La opción de mezclar debe ser un valor booleano.')
        question_limit = data.get('question_limit', 20)
        if question_limit is not None and (type(question_limit) is not int or question_limit < 1):
            raise ValueError('El límite de preguntas debe ser un entero positivo, o null para hacerlas todas.')
        _, bank = read_catalog(self.server.folder)
        if any(name not in bank for name in selected):
            raise ValueError('Un cuestionario ya no existe o contiene errores. Actualiza la lista.')
        session = make_session(bank, selected, count, penalty, shuffle, question_limit=question_limit)
        token = secrets.token_urlsafe(24)
        with self.server.lock:
            self.server.sessions = {key: value for key, value in self.server.sessions.items()
                                    if time.monotonic() - value['created'] < SESSION_TTL}
            if len(self.server.sessions) >= 128:
                oldest = min(self.server.sessions, key=lambda key: self.server.sessions[key]['created'])
                del self.server.sessions[oldest]
            self.server.sessions[token] = session
        self.send_json(200, {'session_id': token, 'questions': public_session(session), 'penalty': penalty})

    def grade(self, data: dict):
        token = data.get('session_id')
        if not isinstance(token, str):
            raise ValueError('Falta la sesión del cuestionario.')
        with self.server.lock:
            session = self.server.sessions.get(token)
        if not session or time.monotonic() - session['created'] >= SESSION_TTL:
            self.send_json(410, {'error': 'La sesión ha caducado o se reinició el programa. Inicia otro cuestionario.'})
            return
        answers = data.get('answers', {})
        if not isinstance(answers, dict):
            raise ValueError('Las respuestas deben ser un objeto JSON.')
        self.send_json(200, grade_session(session, answers))


def main():
    parser = argparse.ArgumentParser(description='Cuestionatron · practica tus cuestionarios Markdown.')
    parser.add_argument('--port', type=int, default=8765, help='Puerto local (por defecto: 8765).')
    parser.add_argument('--no-browser', action='store_true', help='No abrir el navegador automáticamente.')
    parser.add_argument('--folder', type=Path, default=DEFAULT_QUIZ_FOLDER, help='Carpeta de cuestionarios.')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('El puerto debe estar entre 1 y 65535.')
    folder = args.folder.expanduser().resolve()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        server = QuizServer(('127.0.0.1', args.port), folder)
    except OSError as exc:
        parser.exit(1, f'No se pudo iniciar Cuestionatron: {exc}\nPrueba otro puerto con --port 8766.\n')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'\n  Cuestionatron → {url}\n  Cuestionarios: {folder}\n  Pulsa Ctrl+C para cerrar.\n', flush=True)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nCuestionatron cerrado.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
