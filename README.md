# clipengine

## Propósito

**clipengine** es un pipeline gratuito que recibe un video (link de YouTube o archivo local) — pensado sobre todo para **directos musicales de entre 1-4 horas** — y genera automáticamente varios clips verticales (9:16) listos para TikTok/Reels/Shorts, a partir de los momentos de mayor energía de audio (subidas de intensidad musical, aplausos, vítores).

Replica lo que hacen herramientas como OpusClip/Vizard/Klap, pero:
- **gratis en su núcleo**: el análisis de señal (energía + aplausos) corre 100% local, sin llamar a ningún servicio pago.
- **la capa de IA es opcional**: transcripción (Whisper) + LLM (Gemini) para mejorar títulos, selección de momentos y subtítulos quemados — se activa con un flag, y si falla por cualquier motivo (sin API key, sin red, respuesta inválida) el pipeline **nunca se rompe**: cae de vuelta al comportamiento sin IA automáticamente.

Ver `CLAUDE.md` para la propuesta completa de arquitectura y las fases futuras (señal de chat en standby, seguimiento visual, capa de revisión).

- **Fase 1 — núcleo sin IA**: implementada.
- **Fase 2 — capa de IA opcional (transcripción con Whisper + Gemini)**: implementada.

## Requisitos

- Python 3.12 o superior (probado en 3.14)
- [ffmpeg](https://ffmpeg.org/) y `ffprobe` instalados y accesibles desde la terminal (`ffmpeg -version` debe funcionar)
- `git` (para clonar el repositorio)

## Instalación desde cero

### macOS

1. **Python** (si no lo tenés, o tenés una versión anterior a 3.12), vía [Homebrew](https://brew.sh/):
   ```bash
   brew install python@3.13
   ```
2. **ffmpeg**:
   ```bash
   brew install ffmpeg
   ```
3. **Clonar el repo y crear el entorno virtual**:
   ```bash
   git clone <url-del-repo>
   cd long-videos-to-shorts
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

### Windows

1. **Python**: descargá el instalador desde [python.org/downloads](https://www.python.org/downloads/) y marcá la casilla **"Add python.exe to PATH"** durante la instalación — o, con `winget` desde PowerShell:
   ```powershell
   winget install Python.Python.3.13
   ```
2. **ffmpeg**, con `winget`:
   ```powershell
   winget install Gyan.FFmpeg
   ```
   Cerrá y volvé a abrir la terminal para que el `PATH` se actualice, y verificá con `ffmpeg -version`. Si `winget` no está disponible, descargá un build desde [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) y agregá su carpeta `bin` al `PATH` manualmente.
3. **Clonar el repo y crear el entorno virtual** (PowerShell):
   ```powershell
   git clone <url-del-repo>
   cd long-videos-to-shorts
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```
   Si PowerShell bloquea la activación del entorno virtual (error de política de ejecución), corré una vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Capa de IA opcional (Fase 2, cualquier sistema operativo)

Para usar transcripción + Gemini instalá también el extra `ai` (`faster-whisper` + `google-genai`):

```bash
pip install -e ".[ai,dev]"
```

Ver la sección [Capa de IA opcional (Fase 2)](#capa-de-ia-opcional-fase-2) más abajo para configurar la `GEMINI_API_KEY` y las variables relacionadas.

## Uso

```bash
python main.py --input "<url_de_youtube_o_ruta_a_archivo>" --output-dir ./output --num-clips 3
```

Flags disponibles:

| Flag | Descripción |
|---|---|
| `--input` (requerido) | URL (se descarga con `yt-dlp`) o ruta a un archivo local |
| `--output-dir` | Carpeta de salida (default: `./output`) |
| `--num-clips` | Número máximo de clips a generar |
| `--clip-min-duration` | Duración mínima de cada clip (segundos) |
| `--clip-max-duration` | Duración máxima de cada clip (segundos) |

Otros parámetros (duración objetivo, separación mínima entre clips, sensibilidad de detección de picos, pesos de las señales) se ajustan por variable de entorno o en un archivo `.env` — ver `.env.example` para la lista completa y sus defaults.

### Capa de IA opcional (Fase 2)

Con `USE_AI_LAYER=true`, el pipeline transcribe el audio con `faster-whisper` y le pasa la transcripción + los candidatos ya detectados a Gemini, que reordena/filtra y genera títulos y una razón por clip, además de quemar subtítulos en el video donde haya habla:

```bash
export GEMINI_API_KEY=xxxx   # obtener en https://aistudio.google.com/apikey
USE_AI_LAYER=true LLM_PROVIDER=gemini python main.py --input "<url_con_voz>" --output-dir ./output --num-clips 3
```

El título/razón generados por Gemini quedan en `metadata.json` (campos `title`/`reason`), **no** en el nombre del archivo — los `.mp4` siempre se llaman `clip_01.mp4`, `clip_02.mp4`, etc., sea cual sea el resultado de la IA.

**Idioma de la transcripción**: por defecto `WHISPER_LANGUAGE=es`, así Whisper no intenta autodetectar el idioma — algo que puede fallar en directos musicales, porque la autodetección solo mira los primeros ~30s de audio y si ahí hay un intro instrumental o aplausos sin habla clara, puede adivinar mal (ej. transcribir todo en inglés). Si el grupo canta/habla en otro idioma, ajustá `WHISPER_LANGUAGE` (ej. `en`, `fr`) o poné `WHISPER_LANGUAGE=auto` para volver a la autodetección. El título/razón de Gemini, en cambio, siempre se generan en español sin importar `WHISPER_LANGUAGE` ni el idioma real de la transcripción (ver `llm/prompt.py`).

Si falta la API key, `google-genai`/`faster-whisper` no están instalados, hay un error de red, o el LLM devuelve algo inválido, el pipeline **no se rompe**: cae de vuelta al comportamiento de Fase 1 (señal pura + título genérico) y avisa por stderr. La IA es una mejora, nunca una dependencia dura.

**Subtítulos opcionales**: quemar subtítulos es independiente de que la IA rankee/titule los clips — usa `BURN_SUBTITLES=false` para tener títulos/razones de Gemini sin que el pipeline intente grabar subtítulos en el video:

```bash
USE_AI_LAYER=true LLM_PROVIDER=gemini BURN_SUBTITLES=false python main.py --input "<url>" --output-dir ./output
```

### Nota importante sobre los defaults

Los valores por defecto (`CLIP_TARGET_DURATION=40`, `MIN_GAP_SECONDS=45`, etc.) están calibrados para un **directo de ~1 hora**. Si pruebas con un video corto (unos pocos minutos), es probable que se generen menos clips de los que pediste con `--num-clips`, porque no hay espacio suficiente para encontrar picos separados por esa distancia. Para videos cortos, reduce esos valores, por ejemplo:

```bash
CLIP_TARGET_DURATION=10 MIN_GAP_SECONDS=5 PEAK_PROMINENCE=0.02 \
python main.py --input "<url>" --output-dir ./output --num-clips 3 \
  --clip-min-duration 8 --clip-max-duration 15
```

## Qué genera

Con una URL, **el directo completo nunca se descarga** (ver [¿Descarga el video completo?](#descarga-el-video-completo) más abajo):

```
work/
├── source_audio.*    # solo audio del directo completo (gitignored)
├── audio.wav          # audio mono 16kHz extraído, para el análisis
├── clip_01_src.mp4     # solo el rango de video de este clip (unos pocos segundos)
├── clip_02_src.mp4
├── ...
output/
├── clip_01.mp4      # 1080x1920, video H.264 + audio AAC
├── clip_02.mp4
├── ...
└── metadata.json    # timestamps (absolutos, del directo original), score, título y fuente de señal por clip
```

Con un archivo local, `work/` solo tiene `audio.wav` — el archivo de entrada ya está completo en disco, así que se usa directamente para recortar cada clip, sin descargas de por medio.

Ejemplo de `metadata.json`:

```json
{
  "source": { "input": "...", "duration": 177.6 },
  "generated_at": "2026-07-14T19:13:49Z",
  "ai_enhanced": true,
  "clips": [
    {
      "id": 0,
      "file": "clip_01.mp4",
      "start": 42.84,
      "end": 52.84,
      "duration": 10.0,
      "score": 0.3646,
      "title": "Momento destacado 1",
      "reason": null,
      "signal_source": "audio_energy",
      "ai_enhanced": false,
      "has_subtitles": false
    }
  ]
}
```

Sin la capa de IA (o si falló y cayó al fallback), `title` es genérico (`"Momento destacado N"`), `reason` y `ai_enhanced` quedan en `null`/`false`, y `has_subtitles` es `false`. Con la IA activa y funcionando, `title`/`reason` reflejan el contexto real del LLM y `ai_enhanced`/`has_subtitles` pasan a `true` por clip.

## ¿Solo funciona con directos?

No. El pipeline funciona con **cualquier** URL soportada por `yt-dlp` o archivo local — videos normales de YouTube, no solo streams en vivo. Lo que sí está optimizado para música/conciertos es el *análisis de señal*: busca picos de energía sostenida (subidas musicales) y ruido de banda ancha (aplausos/vítores). En un video sin música ni aplausos (charla, tutorial, vlog) el pipeline no falla, pero los "momentos destacados" que encuentre serán simplemente las partes más fuertes de audio, no necesariamente las más interesantes del contenido.

## ¿Descarga el video completo?

No, y esto es importante para directos largos (1-4 horas pueden pesar varios GB). Con una URL, el pipeline nunca baja el archivo de video completo:

1. Primero descarga **solo el audio** del directo entero (`ingest.py::download_audio_only`, formato `bestaudio`) — mucho más liviano que el video (unos pocos MB por hora en vez de varios GB). Con eso corre todo el análisis: energía/aplausos, y si `USE_AI_LAYER=true`, la transcripción con Whisper y el ranking con Gemini.
2. Recién cuando ya se decidieron los clips finales, descarga **solo esos rangos de video** — uno por clip, unos pocos segundos cada uno — usando la opción de rangos de `yt-dlp` (`ingest.py::download_video_segment`, equivalente a `--download-sections`), en vez de todo el archivo.

Con un archivo local no hay nada que optimizar (ya está completo en disco), así que se usa directamente tal cual, sin descargas.

## Arquitectura

```
ingest.py         → resuelve la entrada: para una URL, descarga solo audio (análisis) y
                     luego solo los rangos de video de los clips finales; para un archivo
                     local, lo usa directo
audio_extract.py  → extrae audio mono 16kHz con ffmpeg
energy.py         → energía RMS del audio (librosa)
events.py         → heurística de aplausos/vítores (spectral flatness × RMS, sin IA)
fusion.py         → combina las señales, suaviza la curva, detecta picos locales
candidates.py     → ClipCandidate/RankedClip, ventanas candidatas y selección NMS sin solape
transcribe.py     → transcripción con faster-whisper (solo si USE_AI_LAYER=true)
subtitles.py      → recorta/rebasea segmentos de transcripción por clip y escribe .srt
llm/              → adaptador de LLM: prompt.py (prompt + parseo), gemini.py, dispatcher.py
render.py         → recorta con ffmpeg: crop centrado a 9:16, reencode video + audio + subtítulos opcionales
metadata.py       → escribe metadata.json
pipeline.py       → orquesta todo el flujo (run_pipeline)
cli.py / main.py  → interfaz de línea de comandos
```

Módulos planos, sin subpaquetes anidados salvo `llm/` (el adaptador intercambiable). Agregar un proveedor LLM nuevo (Ollama, Claude, OpenAI, Groq) es un módulo más en `llm/` + una entrada en `llm/dispatcher.py`, sin tocar el resto. La señal de chat (`use_chat_signal`) queda reservada en `config.py` pero en standby, sin implementar (ver `CLAUDE.md`).

## Probar que funciona

**1. Tests automatizados** (unitarios + end-to-end con video sintético generado por `ffmpeg`, sin red, sin API keys, sin descargar modelos reales — todo lo de la capa de IA está mockeado):

```bash
pytest tests/ -v
```

Incluye `test_llm_adapter.py` (parseo de la respuesta del LLM y adaptador de Gemini mockeado), `test_transcribe.py` (wrapper de faster-whisper mockeado), `test_subtitles.py` (recorte/formato SRT) y `test_ingest.py` (opciones exactas que se le pasan a `yt-dlp` para audio-only y para rangos de video, mockeado). A nivel E2E: los casos con `USE_AI_LAYER=true` (uno con la IA funcionando mockeada, otro simulando que falla, para confirmar que el pipeline cae al comportamiento de Fase 1 sin romperse) y `test_pipeline_url_input_never_downloads_full_stream`, que confirma que con una URL solo se llama una vez a la descarga de audio y una vez por clip a la descarga de video — nunca una descarga del directo completo.

`tests/conftest.py` limpia las variables de entorno relacionadas a `clipengine` antes de cada test (vía `autouse` fixture), para que tu `.env` real (con tu `GEMINI_API_KEY`, `BURN_SUBTITLES`, etc.) nunca se filtre a los tests — siempre corren con los defaults del código salvo que el test los fije explícitamente.

**2. Smoke test manual** con un video real corto (5-10 min, con música/aplausos si es posible):

```bash
python main.py --input "<url_corta>" --output-dir ./output_test --num-clips 3
```

### Qué observar al probar

| Qué revisar | Cómo | Qué esperar |
|---|---|---|
| Cantidad de clips | `ls output/` | Depende de cuántos picos "reales" quepan según `CLIP_TARGET_DURATION`/`MIN_GAP_SECONDS` vs. la duración del video |
| Formato/dimensiones | `ffprobe -show_entries stream=width,height clip_01.mp4` | `1080x1920` (o lo que definas en `OUTPUT_WIDTH/HEIGHT`) |
| Audio presente | `ffprobe -show_entries stream=codec_type,codec_name clip_01.mp4` | Debe listar un stream `audio` con `codec_name=aac` |
| Contenido del crop | Reproducir el `.mp4` | Crop centrado (sin seguimiento) — verificar que no corte algo importante si la cámara no está centrada |
| Timestamps con sentido | Comparar `start`/`end` de `metadata.json` contra el video original en ese punto | ¿Es un momento realmente interesante o solo ruido aislado? Es lo más subjetivo; se ajusta con los pesos/umbrales |
| Duración de cada clip | Campo `duration` en `metadata.json` | Entre `CLIP_MIN_DURATION` y `CLIP_MAX_DURATION` |
| Títulos | Campo `title` en `metadata.json` | Genéricos (`"Momento destacado N"`) sin IA; con `USE_AI_LAYER=true` y Gemini funcionando, reflejan el contenido real — revisa `metadata.json`, no el nombre del archivo `.mp4` |

Si los clips no caen donde esperarías, ajusta `ENERGY_WEIGHT`, `APPLAUSE_WEIGHT`, `PEAK_PROMINENCE` y `MIN_GAP_SECONDS` en `.env` y vuelve a correr — es un proceso iterativo (ver sección de riesgos en `CLAUDE.md`).

## Troubleshooting

Si `ffmpeg`/`ffprobe` fallan (descarga, extracción de audio o recorte), la excepción incluye el **stderr real del proceso**, no solo el código de salida — revisa el mensaje completo de la excepción antes de asumir que es un bug del pipeline; casi siempre describe la causa (códec no soportado, archivo corrupto, parámetro inválido, etc.).

**Subtítulos quemados no aparecen aunque `USE_AI_LAYER=true` funcionó bien**: primero confirma que no los desactivaste con `BURN_SUBTITLES=false`. Si no fue eso, es probable que sea el filtro `subtitles` de ffmpeg, que requiere que el binario esté compilado con `libass`. La fórmula estándar `ffmpeg` de Homebrew **no** lo incluye (verifica con `ffmpeg -filters | grep subtitles`; si no aparece nada, confirmado). En macOS, la forma de conseguir un build con soporte es el tap `homebrew-ffmpeg/ffmpeg-full` (no existe una fórmula `ffmpeg-full` suelta en `homebrew-core`):

```bash
brew tap homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg-full/ffmpeg-full
brew link --overwrite ffmpeg-full
```

Mientras tanto, el pipeline detecta el fallo de ffmpeg al quemar subtítulos y **reintenta automáticamente el clip sin ellos** — no se rompe, pero `has_subtitles` en `metadata.json` reflejará `false` para esos clips aunque sí hubiera transcripción disponible.

**La IA no mejora nada y los títulos siguen siendo genéricos**: revisa el mensaje de aviso en stderr (`[clipengine] Aviso: ...`) — casi siempre es `GEMINI_API_KEY` no configurada, `google-genai`/`faster-whisper` no instalados (`pip install -e ".[ai]"`), o el LLM devolvió una respuesta que no se pudo parsear como JSON. En cualquier caso `ai_enhanced` queda en `false` en el JSON, y eso es el comportamiento esperado de degradación, no un error a corregir.
