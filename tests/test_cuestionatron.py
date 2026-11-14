import http.client
import json
from pathlib import Path
import random
import tempfile
import threading
import unittest

from cuestionatron import (
    QuizFormatError, QuizServer, grade_session, make_session, parse_quiz,
    public_session, read_catalog,
)


SAMPLE = """# Una sola correcta
+ Correcta
- Incorrecta A
- Incorrecta B
- Incorrecta C
- Incorrecta D

# Varias correctas
+ Primera
+ Segunda
+ Tercera
- Falsa A
- Falsa B
- Falsa C
"""


class ParserTests(unittest.TestCase):
    def test_single_and_multiple_with_bom_whitespace_and_no_spaces(self):
        questions = parse_quiz('\ufeff\n  # Pregunta(Con nombre) \n+Sí\n- No\n\n#Otra\n+Uno\n+Dos\n-Tres\n')
        self.assertEqual(questions[0].text, 'Pregunta(Con nombre)')
        self.assertEqual(questions[0].answers[0].text, 'Sí')
        self.assertEqual(sum(a.correct for a in questions[1].answers), 2)

    def test_rejects_invalid_files_with_clear_errors(self):
        for source, message in [
            ('', 'no contiene preguntas'),
            ('# Pregunta\n- No', 'Línea 1'),
            ('# Pregunta\n+ Sí', 'respuesta con -'),
            ('+ Respuesta', 'antes de la primera'),
            ('#\n+ Sí\n- No', 'falta el enunciado'),
            ('# Pregunta\n+\n- No', 'respuesta está vacía'),
            ('# Pregunta\n+ Igual\n- igual', 'respuestas repetidas'),
            ('# Pregunta\n+ Sí\n- No\ntexto libre', 'Línea 4'),
            ('# Una\n+ Sí\n- No\n# Dos\n- No', 'Línea 4'),
        ]:
            with self.subTest(source=source), self.assertRaisesRegex(QuizFormatError, message):
                parse_quiz(source)

    def test_twenty_distractors_are_supported(self):
        questions = parse_quiz('# Pregunta\n+ Correcta\n' + '\n'.join(f'- Error {i}' for i in range(20)))
        self.assertEqual(len(questions[0].answers), 21)

    def test_catalog_separates_invalid_files_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'Válido.md').write_text(SAMPLE, encoding='utf-8')
            (folder / 'Roto.md').write_text('# Incompleta\n- Falsa', encoding='utf-8')
            (folder / 'Ignorar.txt').write_text(SAMPLE, encoding='utf-8')
            (folder / 'Subcarpeta').mkdir()
            (folder / 'Subcarpeta' / 'Oculto.md').write_text(SAMPLE, encoding='utf-8')
            (folder / 'Enlace.md').symlink_to(folder / 'Válido.md')
            catalog, bank = read_catalog(folder)
        self.assertEqual(set(bank), {'Válido.md'})
        self.assertEqual(len(catalog), 2)
        self.assertTrue(next(q for q in catalog if q['id'] == 'Roto.md')['error'])
        valid = next(q for q in catalog if q['id'] == 'Válido.md')
        self.assertEqual((valid['count'], valid['multiple']), (2, 1))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.bank = {'Uno.md': parse_quiz(SAMPLE)}

    def session(self, count=4, penalty=.5):
        return make_session(self.bank, ['Uno.md'], count, penalty, False, random.Random(9))

    def test_preserves_all_correct_options_and_keeps_at_least_one_incorrect(self):
        session = self.session(count=2)
        single, multiple = session['questions']
        self.assertEqual(len(single['options']), 2)
        self.assertEqual(len(multiple['options']), 4)
        self.assertEqual(sum(a['correct'] for a in multiple['options']), 3)

    def test_requested_count_is_capped_by_available_options(self):
        self.assertEqual(len(self.session(count=21)['questions'][0]['options']), 5)

    def test_random_sampling_draws_different_options_without_duplicates(self):
        samples = set()
        for seed in range(20):
            question = make_session(self.bank, ['Uno.md'], 3, 0, True, random.Random(seed))['questions']
            single = next(q for q in question if not q['multiple'])
            texts = [a['text'] for a in single['options']]
            self.assertEqual(len(texts), len(set(texts)))
            self.assertIn('Correcta', texts)
            samples.add(tuple(texts))
        self.assertGreater(len(samples), 1)

    def test_combines_files_and_preserves_order_when_requested(self):
        self.bank['Dos.md'] = parse_quiz('# Otra\n+ Bien\n- Mal')
        session = make_session(self.bank, ['Dos.md', 'Uno.md'], 4, 0, False)
        self.assertEqual([q['source'] for q in session['questions']], ['Dos', 'Uno', 'Uno'])
        self.assertEqual(len({q['id'] for q in session['questions']}), 3)

    def test_public_questions_do_not_expose_correctness(self):
        for question in public_session(self.session()):
            for option in question['options']:
                self.assertEqual(set(option), {'id', 'text'})

    def test_large_bank_defaults_to_twenty_questions(self):
        bank = {'Cien.md': parse_quiz('\n'.join(f'# Pregunta {i}\n+ Sí\n- No' for i in range(100)))}
        session = make_session(bank, ['Cien.md'], 2, 0, False, random.Random(7))
        self.assertEqual(len(session['questions']), 20)
        positions = [int(q['text'].split()[-1]) for q in session['questions']]
        self.assertEqual(positions, sorted(set(positions)))
        self.assertNotEqual(positions, list(range(20)))

    def test_custom_limit_applies_to_combined_pool_and_score(self):
        bank = {name: parse_quiz('\n'.join(f'# {name} {i}\n+ Sí\n- No' for i in range(50)))
                for name in ('Uno.md', 'Dos.md')}
        session = make_session(bank, list(bank), 2, .2, True, random.Random(4), question_limit=7)
        self.assertEqual(len(session['questions']), 7)
        self.assertEqual({q['source'] for q in session['questions']}, {'Uno', 'Dos'})
        answers = {q['id']: [a['id'] for a in q['options'] if a['correct']] for q in session['questions']}
        result = grade_session(session, answers)
        self.assertEqual((result['total'], result['correct'], result['score']), (7, 7, 10))
        all_questions = make_session(bank, list(bank), 2, 0, False, question_limit=None)
        self.assertEqual(len(all_questions['questions']), 100)
        short_bank = make_session(self.bank, ['Uno.md'], 2, 0, False, question_limit=100)
        self.assertEqual(len(short_bank['questions']), 2)

    def test_full_marks_and_exact_multiple_combination(self):
        session = self.session()
        answers = {q['id']: [a['id'] for a in q['options'] if a['correct']] for q in session['questions']}
        result = grade_session(session, answers)
        self.assertEqual((result['score'], result['correct']), (10, 2))
        multiple = session['questions'][1]
        answers[multiple['id']] = answers[multiple['id']][:-1]
        result = grade_session(session, answers)
        self.assertEqual((result['correct'], result['incorrect'], result['score']), (1, 1, 2.5))

    def test_extra_incorrect_option_makes_multiple_answer_wrong(self):
        session = self.session()
        question = session['questions'][1]
        result = grade_session(session, {question['id']: [a['id'] for a in question['options']]})
        self.assertEqual((result['incorrect'], result['blank']), (1, 1))

    def test_blank_answers_do_not_subtract_and_score_cannot_be_negative(self):
        session = self.session(penalty=10)
        blank = grade_session(session, {})
        self.assertEqual((blank['score'], blank['blank'], blank['net']), (0, 2, 0))
        question = session['questions'][0]
        wrong = next(a['id'] for a in question['options'] if not a['correct'])
        result = grade_session(session, {question['id']: [wrong]})
        self.assertEqual((result['score'], result['net'], result['blank']), (0, -10, 1))

    def test_documented_scoring_example(self):
        bank = {'Diez.md': parse_quiz('\n'.join(f'# Pregunta {i}\n+ Sí\n- No' for i in range(10)))}
        session = make_session(bank, ['Diez.md'], 2, .5, False)
        answers = {}
        for i, question in enumerate(session['questions'][:9]):
            answers[question['id']] = [next(a['id'] for a in question['options'] if a['correct'] == (i < 7))]
        result = grade_session(session, answers)
        self.assertEqual((result['correct'], result['incorrect'], result['blank'], result['score']), (7, 2, 1, 6))

    def test_invalid_answers_are_rejected(self):
        session = self.session()
        question = session['questions'][0]
        for answers in [{'unknown': []}, {question['id']: ['nope']}, {question['id']: '0'},
                        {question['id']: [['0']]}, {question['id']: ['0', '0']},
                        {question['id']: ['0', '1']}]:
            with self.subTest(answers=answers), self.assertRaises(ValueError):
                grade_session(session, answers)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        (cls.folder / 'Prueba.md').write_text(SAMPLE, encoding='utf-8')
        cls.server = QuizServer(('127.0.0.1', 0), cls.folder)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(self, method, path, data=None, extra_headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Content-Type': 'application/json', **(extra_headers or {})}
        conn.request(method, path, body=json.dumps(data) if data is not None else None, headers=headers)
        response = conn.getresponse()
        status, body, content_type = response.status, response.read(), response.getheader('Content-Type')
        conn.close()
        return status, json.loads(body) if 'application/json' in (content_type or '') else body

    def config(self, **updates):
        return {'quizzes': ['Prueba.md'], 'answer_count': 4, 'penalty': .33, 'shuffle': True, **updates}

    def test_catalog_start_answer_grade_flow(self):
        status, catalog = self.request('GET', '/api/catalog')
        self.assertEqual(status, 200)
        self.assertEqual(catalog['quizzes'][0]['count'], 2)
        status, session = self.request('POST', '/api/start', self.config())
        self.assertEqual(status, 200)
        self.assertEqual(len(session['questions']), 2)
        self.assertNotIn('correct', session['questions'][0]['options'][0])
        # Las opciones conocidas del archivo permiten un intento completo por HTTP.
        answers = {q['id']: [a['id'] for a in q['options'] if a['text'] in ('Correcta', 'Primera', 'Segunda', 'Tercera')]
                   for q in session['questions']}
        status, result = self.request('POST', '/api/grade', {'session_id': session['session_id'], 'answers': answers})
        self.assertEqual(status, 200)
        self.assertEqual(result['score'], 10)
        self.assertEqual(len(result['review']), 2)

    def test_bad_configuration_and_path_traversal_are_rejected(self):
        for updates in [{'quizzes': []}, {'quizzes': ['../Prueba.md']}, {'quizzes': ['Prueba.md', 'Prueba.md']},
                        {'quizzes': [1]}, {'answer_count': 1}, {'answer_count': 22}, {'answer_count': True},
                        {'penalty': -1}, {'penalty': float('nan')}, {'penalty': '0.5'}, {'shuffle': 'yes'},
                        {'question_limit': 0}, {'question_limit': -1}, {'question_limit': True},
                        {'question_limit': 2.5}, {'question_limit': '20'}]:
            with self.subTest(updates=updates):
                status, _ = self.request('POST', '/api/start', self.config(**updates))
                self.assertEqual(status, 400)

    def test_http_question_limit_and_all_questions_option(self):
        status, session = self.request('POST', '/api/start', self.config(question_limit=1))
        self.assertEqual((status, len(session['questions'])), (200, 1))
        status, result = self.request('POST', '/api/grade', {'session_id': session['session_id'], 'answers': {}})
        self.assertEqual((status, result['total']), (200, 1))
        status, session = self.request('POST', '/api/start', self.config(question_limit=None))
        self.assertEqual((status, len(session['questions'])), (200, 2))

    def test_custom_penalty_outside_presets_is_applied_to_score(self):
        status, session = self.request('POST', '/api/start', self.config(penalty=.175))
        self.assertEqual(status, 200)
        self.assertEqual(session['penalty'], .175)
        answers = {}
        for question in session['questions']:
            # Acierta la pregunta simple y falla la múltiple con una opción incorrecta.
            expected = 'Falsa' if question['multiple'] else 'Correcta'
            answers[question['id']] = [next(a['id'] for a in question['options']
                                           if a['text'].startswith(expected))]
        status, result = self.request('POST', '/api/grade', {'session_id': session['session_id'], 'answers': answers})
        self.assertEqual(status, 200)
        self.assertEqual((result['correct'], result['incorrect'], result['penalty']), (1, 1, .175))
        self.assertEqual(result['score'], round((1 - .175) / 2 * 10, 2))

    def test_static_assets_are_available_but_source_files_are_not(self):
        for path in ['/', '/style.css', '/app.js', '/favicon.svg', '/ganso-bailon.gif', '/celebracion.mp3']:
            with self.subTest(path=path):
                status, body = self.request('GET', path)
                self.assertEqual(status, 200)
                self.assertTrue(body)
        for path in ['/../cuestionatron.py', '/Cuestionarios/Prueba.md', '/api/nope', '/%2e%2e/README.md']:
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], 404)

    def test_unknown_sessions_and_foreign_origins(self):
        self.assertEqual(self.request('POST', '/api/grade', {'session_id': 'expired', 'answers': {}})[0], 410)
        self.assertEqual(self.request('POST', '/api/start', self.config(), {'Origin': 'https://example.org'})[0], 403)

    def test_sessions_are_snapshots_after_files_change(self):
        status, session = self.request('POST', '/api/start', self.config())
        self.assertEqual(status, 200)
        original = (self.folder / 'Prueba.md').read_text(encoding='utf-8')
        try:
            (self.folder / 'Prueba.md').write_text('# Rota', encoding='utf-8')
            status, result = self.request('POST', '/api/grade', {'session_id': session['session_id'], 'answers': {}})
            self.assertEqual((status, result['total'], result['blank']), (200, 2, 2))
            self.assertEqual(self.request('POST', '/api/start', self.config())[0], 400)
        finally:
            (self.folder / 'Prueba.md').write_text(original, encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
