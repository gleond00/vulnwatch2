# GEAH - Instalación

## 1. Aplicación

## 2. Servicio Web App

## 3. Servicio HL7 MLLP

### Autoarranque Windows

#### Programador de Tareas

Abrirlo de una de estas maneras:

- Menú de Windows > Programador de Tareas
- Administrador de Tareas (Ctrl+Shift+Esc) > Ejecutar nueva tarea : `%windir%\system32\taskschd.msc /s`

##### Crear tarea en el programador

Dos opciones:

- Crear nueva en la biblioteca de tareas:

  - Lateral izquierdo > Biblioteca del programador de tareas > pulsar botón derecho > Crear Tarea
  - Menú Acción > Crear Tarea

- Importar tarea guardada desde un archivo.

###### Creando Tarea nueva

Pestañas:

    General
        nombre:     [TICKETS, cmax211014@outlook.es ...]
        Opciones de seguridad:
            Usuario:   [TICKETS, cmax211014@outlook.es ...]
            Ejecutar tanto cuando el usuario haya iniciado sesión como si no
            Ejecutar con los privilegios más altos
        Oculta:     [marcar]
        Configurar para:   [Windows 10]
    Desencadenadores:
        Opción 1 (preferido):
                Iniciar tarea:    [Al iniciar el sistema]
                Configuración avanzada:
                    Repetir cada:  [1 minutos]
                    durante:  [Indefinidamente]
        Opción 2: ¡requiere autologin!
            Nuevo
                Iniciar tarea:    [Al iniciar la sesión]
                Configuración:
                    Usuario específico:  [geah ...]
                Configuración avanzada:
                    Repetir cada:  [1 minutos]
                    durante:  [Indefinidamente]
    Desactivar todos los cuadros de chequeo EXCEPTO 'Repetir cada' y 'Habilitado'
    Acciones:
        Nueva:
            Acción:     [Iniciar un programa]
            Programa o script:  [C:\Python310\pythonw.exe]
            Agregar argumentos: [hl7service.pyc]
            Iniciar en:         [C:\geah-project\]
    Condiciones:
        Desactivar todos los cuadros de chequeo
    Configuración:
        Desactivar todo EXCEPTO:
            'Permitir que la tarea se ejecute a petición'
            'Ejecutar lo antes posible si no hubo reinicio programado'
        En desplegable final, seleccionar:
            'No iniciar una instancia nueva'
