/* Lanzador Windows x64 sin dependencias de un compilador o Python instalado.
 * Usa solo Win32 y arranca el Python portable incluido en _interno/python.
 */
typedef __WCHAR_TYPE__ WCHAR;
typedef unsigned long DWORD;
typedef unsigned short WORD;
typedef int BOOL;
typedef void *HANDLE;
typedef struct {
    DWORD cb;
    WCHAR *lpReserved, *lpDesktop, *lpTitle;
    DWORD dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars;
    DWORD dwFillAttribute, dwFlags;
    WORD wShowWindow, cbReserved2;
    unsigned char *lpReserved2;
    HANDLE hStdInput, hStdOutput, hStdError;
} STARTUPINFOW;
typedef struct {
    HANDLE hProcess, hThread;
    DWORD dwProcessId, dwThreadId;
} PROCESS_INFORMATION;

#define DLL __declspec(dllimport)
DLL DWORD __stdcall GetModuleFileNameW(HANDLE, WCHAR *, DWORD);
DLL DWORD __stdcall GetFileAttributesW(const WCHAR *);
DLL BOOL __stdcall SetEnvironmentVariableW(const WCHAR *, const WCHAR *);
DLL BOOL __stdcall CreateProcessW(const WCHAR *, WCHAR *, void *, void *, BOOL,
                                 DWORD, void *, const WCHAR *, STARTUPINFOW *, PROCESS_INFORMATION *);
DLL DWORD __stdcall WaitForSingleObject(HANDLE, DWORD);
DLL BOOL __stdcall GetExitCodeProcess(HANDLE, DWORD *);
DLL BOOL __stdcall CloseHandle(HANDLE);
DLL __declspec(noreturn) void __stdcall ExitProcess(DWORD);
DLL int __stdcall MessageBoxW(HANDLE, const WCHAR *, const WCHAR *, unsigned int);

#define CAPACITY 32768
static WCHAR base[CAPACITY], python[CAPACITY], script[CAPACITY], command[CAPACITY];
static STARTUPINFOW startup;
static PROCESS_INFORMATION process;

static void fail(const WCHAR *message) {
    MessageBoxW(0, message, L"Cuestionatron", 0x10);
    ExitProcess(1);
}

static void append(WCHAR *target, const WCHAR *source) {
    unsigned int i = 0, j = 0;
    while (target[i]) ++i;
    while (source[j]) {
        if (i >= CAPACITY - 1) fail(L"La ruta es demasiado larga. Extrae Cuestionatron en una carpeta más corta.");
        target[i++] = source[j++];
    }
    target[i] = 0;
}

void entry(void) {
    DWORD size = GetModuleFileNameW(0, base, CAPACITY);
    if (!size || size >= CAPACITY) fail(L"No se pudo localizar la carpeta del programa.");
    while (size && base[size - 1] != L'\\' && base[size - 1] != L'/') --size;
    if (!size) fail(L"No se pudo localizar la carpeta del programa.");
    base[size] = 0;
    append(python, base);
    append(python, L"_interno\\python\\pythonw.exe");
    append(script, base);
    append(script, L"_interno\\app\\escritorio.py");
    if (GetFileAttributesW(python) == 0xffffffffUL || GetFileAttributesW(script) == 0xffffffffUL)
        fail(L"Faltan archivos del programa. Extrae todo el ZIP antes de abrir Cuestionatron.exe y conserva la carpeta _interno junto al ejecutable.");
    if (!SetEnvironmentVariableW(L"CUESTIONATRON_HOME", base))
        fail(L"No se pudo preparar la carpeta de Cuestionatron.");
    append(command, L"\"");
    append(command, python);
    append(command, L"\" -I \"");
    append(command, script);
    append(command, L"\"");
    startup.cb = sizeof(startup);
    if (!CreateProcessW(python, command, 0, 0, 0, 0x08000000UL, 0, base, &startup, &process))
        fail(L"No se pudo iniciar Cuestionatron. Comprueba que has extraído todo el ZIP y utilizas Windows de 64 bits.");
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, 0xffffffffUL);
    DWORD result = 1;
    GetExitCodeProcess(process.hProcess, &result);
    CloseHandle(process.hProcess);
    if (result) fail(L"Cuestionatron se cerró con un error. Conserva todas las carpetas del ZIP y vuelve a intentarlo desde una carpeta donde puedas guardar archivos.");
    ExitProcess(0);
}
