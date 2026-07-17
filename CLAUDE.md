# Propuesta de implementación: pipeline propio de recorte de clips para directos musicales

## 1. Objetivo

Construir un sistema propio, gratuito en su núcleo, que reciba un directo musical de entre 1-4 horas (link o archivo) y produzca automáticamente varios clips verticales (9:16) listos para TikTok/Reels/Shorts — replicando lo que hacen OpusClip/Vizard/Klap, pero adaptado a contenido musical (algo que esas herramientas comerciales no cubren bien) y sin costos de suscripción.

La capa de razonamiento con IA es **opcional** y **agnóstica de proveedor**: el sistema debe producir clips razonables únicamente con análisis de señal (gratis, sin llamar a ningún LLM), y mejorar su calidad de selección/naming si se activa la capa de IA — sea con Claude, Gemini, OpenAI, un modelo local, o cualquier otro proveedor compatible.

---

## 2. Arquitectura general

```
 ┌────────────────────┐
 │ 1. Entrada           │  link (yt-dlp) o archivo
 └─────────┬────────────┘
           │
 ┌─────────▼────────────┐
 │ 2. Extracción de audio│  ffmpeg
 └─────────┬────────────┘
           │
 ┌─────────▼─────────────────────────────────────────┐
 │ 3. Análisis de señales (en paralelo)                │
 │                                                      │
 │  a) Energía + aplausos       b) Chat / clips de      │
 │     (librosa, siempre activo)   plataforma           │
 │                                  (en standby, no      │
 │                                   implementada)       │
 │  c) [OPCIONAL] Whisper + LLM                         │
 │     transcripción + razonamiento sobre contexto      │
 │     (proveedor configurable)                          │
 └─────────┬───────────────────────────────────────────┘
           │
 ┌─────────▼────────────┐
 │ 4. Fusión y selección │  score de interés → clips candidatos
 └─────────┬────────────┘
           │
 ┌─────────▼────────────┐
 │ 5. Recorte con FFmpeg │  corte, crop 9:16, subtítulos (si aplica)
 └─────────┬────────────┘
           │
 ┌─────────▼────────────┐
 │ 6. Salida             │  clips + JSON de metadata (timestamps, score, título)
 └────────────────────────┘
```

---

## 3. Flujo del sistema, etapa por etapa

### 3.1 Entrada
- Link de YouTube/Twitch → descarga con `yt-dlp`, pero **nunca el directo completo** *(implementado)*: primero se baja solo el audio (formato `bestaudio`, liviano) para correr todo el análisis; recién cuando ya se decidieron los clips finales se descarga, por cada uno, solo su rango de video puntual (vía la opción de rangos de `yt-dlp`, equivalente a `--download-sections`). Un directo de 1-4 horas pesa varios GB en video completo pero solo unos pocos MB por hora en audio — evitar la descarga completa es relevante en ese volumen.
- Archivo local → se usa directamente (ya está completo en disco, no hay nada que optimizar).
- *(En standby, no implementado — ver sección 8)* Si el directo fue en Twitch/YouTube Live, la idea original era descargar también el **replay del chat** (mensajes con timestamp) como señal adicional gratuita. Se pospuso porque el chat no suele ser lo bastante activo en estos directos como para aportar señal útil; el pipeline hoy no descarga ni usa datos de chat en ningún punto.

### 3.2 Extracción de audio
- `ffmpeg` separa el audio (mono, 16 kHz) de la fuente de audio ya descargada (o del archivo local) para que el análisis no tenga que cargar el video completo. Es rápido y no requiere GPU.

### 3.3 Análisis de señales (motor de detección de momentos)
Tres fuentes de señal, diseñadas para funcionar de forma independiente:

| Señal | Herramienta | ¿Requiere IA generativa? | ¿Siempre disponible? |
|---|---|---|---|
| Energía de audio (picos RMS) | `librosa` (RMS) | No | Sí, siempre |
| Aplausos/vítores | `librosa` — heurística de ruido de banda ancha (spectral flatness alta) × energía sostenida (RMS alto) | No | Sí, siempre |
| Chat / clips ya creados por la audiencia | API de Twitch/YouTube | No | **En standby, no implementada** — ver sección 8 |
| Transcripción + razonamiento contextual | `faster-whisper` (gratis, local) + **LLM configurable** (opcional) | Sí, la parte de razonamiento | Solo si se activa la opción de IA |

> **Nota (implementación real, difiere de la propuesta inicial)**: para la detección de aplausos se descartó a propósito un clasificador de eventos de audio tipo YAMNet/PANNs — esa ruta exige TensorFlow/PyTorch como dependencia pesada solo para una señal que, en la práctica, se resuelve bien con una heurística de señal (spectral flatness × RMS) sin ningún modelo de aprendizaje profundo. Mantiene la Fase 1 100% libre de dependencias de IA, incluso locales. Ver `src/clipengine/events.py`.

### 3.4 Fusión y selección
- Las señales sin IA (energía + aplausos — la señal de chat de la tabla anterior está en standby y no participa en la fusión) se normalizan y se combinan en una sola curva de "interés" por segundo. Los picos locales de esa curva son los clips candidatos — esto **ya funciona sin gastar un centavo en IA**.
- Si la capa de IA está activada, el LLM configurado recibe la transcripción + los timestamps de los picos ya detectados, y:
  - Reordena/filtra los candidatos usando el contexto (ej. "la banda anuncia que toca su tema más conocido").
  - Genera un título/hook sugerido para cada clip.
  - Da una breve razón de por qué ese momento es interesante (similar al "Virality Score" de OpusClip, pero explicado en texto).
- Si la capa de IA está desactivada, el sistema simplemente ordena los candidatos por el score de energía/aplausos y genera un título genérico (ej. "Momento destacado 1", con el timestamp).

### 3.5 Recorte con FFmpeg
- Corte del segmento (`-ss` / `-to`, reencodeado para precisión de frame).
- Reencuadre a 9:16 — crop centrado por defecto (más simple y confiable para música que el seguimiento de rostro, que no aplica bien a un escenario/DJ set).
- Subtítulos quemados en el video **solo si hubo transcripción** (es decir, solo si la capa de IA/Whisper estuvo activa y hay partes habladas).

### 3.6 Salida
- Clips en `.mp4`, formato 9:16.
- Un archivo JSON con metadata de cada clip (inicio, fin, score, título, fuente de la señal que lo generó) — *implementado hoy*; pensado para que, más adelante, la capa de revisión (React/Supabase, Fase 5, **no implementada todavía**) pueda mostrarlos antes de publicar.

---

## 4. La capa de IA: agnóstica de proveedor

Este pipeline **no depende de un único proveedor de IA**. La integración se diseña como un adaptador intercambiable: el resto del sistema le pasa "transcripción + timestamps candidatos" y espera de vuelta "lista de clips rankeados con título", sin importar qué modelo hizo el trabajo. Cambiar de proveedor debería ser cuestión de cambiar una variable de configuración, no de reescribir código.

### 4.1 Un principio que aplica a todos los proveedores grandes

Vale la pena aclarar esto una sola vez porque aplica igual a Claude, Gemini y OpenAI: **la suscripción de chat (Claude Pro, Gemini Advanced, ChatGPT Plus) no da acceso a la API de desarrollador.** Son productos separados con facturación separada:

| Proveedor | Suscripción de chat (no sirve para este pipeline) | API de desarrollador (lo que sí necesita el pipeline) |
|---|---|---|
| Anthropic | Claude Pro/Max ($20–200/mes) | `platform.claude.com` — pago por token, **sin capa gratuita permanente** (solo un crédito inicial pequeño de prueba) |
| Google | Gemini Advanced (incluido en Google One) | Google AI Studio (`ai.google.dev`) — **sí tiene capa gratuita permanente** en los modelos Flash |
| OpenAI | ChatGPT Plus ($20/mes) | `platform.openai.com` — pago por token, capa gratuita prácticamente inutilizable (limitada a GPT-3.5 con límites muy bajos) |

### 4.2 Comparativa de modelos gratuitos para esta tarea específica

La tarea que le pedimos al LLM es modesta en exigencia: leer una transcripción de ~1 hora (unos pocos miles de tokens), cruzarla con los timestamps que ya detectó el análisis de señal, y devolver una lista rankeada en JSON con títulos. No requiere el modelo más avanzado del mercado — esto abre varias opciones genuinamente gratuitas:

| Opción | Costo real | Calidad para esta tarea | Privacidad | Notas |
|---|---|---|---|---|
| **Google Gemini (Flash / Flash-Lite)** | Gratis, capa permanente, sin tarjeta | Buena — de sobra para ranking + generación de títulos | Los datos de la capa gratuita pueden usarse para entrenar los modelos de Google | La opción gratuita más simple de configurar; recomendada para empezar |
| **Modelo local vía Ollama** (Llama 3.x, Qwen 2.5/3, Mistral, DeepSeek) | Gratis, sin límites de uso, corre en tu propia máquina | Buena en modelos de 7B+ para esta tarea (no es razonamiento complejo) | **Total** — nada sale de tu computadora | La opción más privada; requiere una PC con al menos 8-16 GB de RAM (mejor con GPU, pero modelos pequeños corren en CPU) |
| **Groq (modelos open-weight: Llama 3.3 70B, Qwen3, GPT-OSS)** | Gratis, capa permanente, sin tarjeta | Buena, modelos de tamaño considerable | Datos procesados en la nube de Groq | La inferencia más rápida del mercado; buena opción si prefieres no instalar nada localmente |
| **Mistral (plan "Experiment")** | Gratis, ~1,000 millones de tokens/mes | Aceptable | Los datos pueden usarse para entrenamiento | Volumen muy generoso, pero calidad algo por debajo de Gemini Flash para tareas de razonamiento |
| OpenAI (capa gratuita) | Prácticamente inutilizable (límites muy bajos, solo GPT-3.5) | — | — | No se recomienda como opción gratuita real |
| Anthropic (Claude API) | Sin capa gratuita permanente, solo crédito inicial de prueba | La mejor calidad de razonamiento contextual de las evaluadas | Datos procesados en la nube de Anthropic | Recomendado si ya se decidió pagar por la mejor calidad posible, no como opción gratuita |

**Recomendación concreta:**
- **Para arrancar sin gastar nada y sin instalar software adicional**: Gemini Flash (API gratuita de Google AI Studio). Es la opción con mejor relación de esfuerzo de configuración vs. calidad.
- **Si la privacidad del repertorio/contenido del grupo es una prioridad** (nada sale de tu equipo): modelo local vía Ollama. Es la opción con cero dependencia de terceros, a cambio de necesitar algo de configuración y hardware razonable.
- **Si más adelante se quiere la mejor calidad posible** (mejor comprensión de contexto, menos necesidad de ajustar prompts): Claude o GPT de pago, aceptando el costo por token.

### 4.3 Diseño del adaptador

Siguiendo el mismo patrón que usa el proyecto de referencia (ver sección 6), la integración se resuelve con una función despachadora simple:

```
LLM_PROVIDER = "gemini" | "groq" | "ollama" | "openai" | "claude" | ...
```

Cada proveedor implementa la misma interfaz (`rank_and_title(transcript, candidate_timestamps) -> list[clip]`), y el resto del pipeline no necesita saber cuál está activo. Agregar un proveedor nuevo es escribir una función más, sin tocar el resto del sistema.

> **Estado actual**: de esa lista, solo `"gemini"` está implementado (`src/clipengine/llm/gemini.py`, registrado en `llm/dispatcher.py`). `"groq"`, `"ollama"`, `"openai"` y `"claude"` son el diseño previsto para el adaptador, no código que exista hoy — si se configura `LLM_PROVIDER` con cualquiera de esos valores, el dispatcher no falla ni lanza una excepción: detecta que el proveedor no está registrado, avisa por stderr y cae a la selección por señal pura, exactamente igual que si `USE_AI_LAYER=false`.

---

## 5. Diseño para que la IA sea opcional

Esto se resuelve con un flag de configuración, independiente de qué proveedor se elija:

```
USE_AI_LAYER = true | false
LLM_PROVIDER = "gemini" | "groq" | "ollama" | "openai" | "claude"   # solo relevante si USE_AI_LAYER=true
```

| | `USE_AI_LAYER=false` (por defecto, gratis) | `USE_AI_LAYER=true` (requiere configurar Gemini — único proveedor implementado hoy, ver sección 4.3) |
|---|---|---|
| Selección de momentos | Solo señal (energía + aplausos) | Señal + razonamiento del LLM sobre la transcripción |
| Títulos de los clips | Genéricos (timestamp) | Generados con contexto ("hook" sugerido) |
| Subtítulos | No (no hay transcripción) | Sí, quemados desde la transcripción de Whisper |
| Costo adicional | $0 | $0 a centavos por directo con Gemini (ver sección 4.2) |
| Requiere | Solo librerías locales | Una API key de Gemini (`GEMINI_API_KEY`) |

El sistema debe funcionar de punta a punta con `USE_AI_LAYER=false` — la IA es una mejora, no una dependencia. Esto también significa que la parte de Whisper (transcripción) solo se ejecuta si la capa de IA está activada, ya que sin un LLM esa transcripción no se usa para nada.

---

## 6. Proyecto de referencia

Como referencia de arquitectura (no como base que se vaya a clonar ni depender directamente de él) se tomará **`SamurAIGPT/AI-Youtube-Shorts-Generator`**, un proyecto open source (MIT, ~3-4 mil estrellas en GitHub, mantenimiento activo) que resuelve un problema equivalente para contenido hablado. De ahí se toman ideas de diseño, entre ellas:

- La separación clara entre **descarga → transcripción → capa de razonamiento con LLM → recorte/crop → salida en JSON**, que es una estructura sólida y reutilizable.
- El patrón de tener un **modo local totalmente offline** (sin depender de un servicio de terceros) frente a un modo que usa una API externa — la misma idea que aplicamos aquí con el flag `USE_AI_LAYER`.
- Su selector de proveedor de LLM (en ese proyecto, entre OpenAI y Gemini mediante una variable de entorno) — es exactamente el patrón de adaptador intercambiable que proponemos extender en la sección 4.3 para soportar también Claude, Groq y modelos locales.
- El formato de salida en JSON con metadata por clip (score, título, timestamps), útil para conectar con una capa de revisión.

Lo que **no** se reutiliza de ese proyecto:
- Su dependencia de MuAPI (servicio de pago de terceros) — nuestro pipeline no la necesita.
- Su lógica de selección de momentos, orientada a diálogo — se reemplaza por el motor de señales musicales descrito en la sección 3.3 (energía + aplausos, implementados; la señal de chat de esa misma sección sigue en standby).
- Su reencuadre por seguimiento de rostro — se reemplaza por un crop centrado, más adecuado para un escenario o set de DJ.

---

## 7. Stack técnico propuesto

- **Worker de análisis y recorte** *(implementado, Fases 1-2)*: Python (`yt-dlp`, `librosa`, `faster-whisper` opcional, `ffmpeg` vía `subprocess`), más un adaptador de LLM intercambiable — hoy solo con el SDK oficial de Gemini; un cliente HTTP local para Ollama es diseño previsto (sección 4.3), no código existente.
- **Orquestación / metadata / revisión** *(Fase 5, no implementada)*: Node.js + Supabase, siguiendo el mismo patrón que ya usas para tu librería de clips — cada directo procesado generaría un registro con sus clips candidatos, y una interfaz en React para revisar/aprobar antes de publicar. Hoy la única salida es el `metadata.json` local descrito en la sección 3.6.
- **Salida** *(Fase 5, no implementada)*: archivos `.mp4` en almacenamiento (local o Supabase Storage) + tabla de metadata en Supabase. Hoy los `.mp4` y el `metadata.json` quedan solo en el filesystem local (`output_dir`).

---

## 8. Fases de implementación sugeridas

Cada fase tiene criterios de aceptación concretos y verificables (código + tests automatizados). Una fase se marca *(implementada)* solo cuando todos sus criterios están cumplidos; el estado se revisa contra el código real, no contra la intención original.

### Fase 1 — Núcleo sin IA *(implementada)*

**Criterios de aceptación:**
- [x] Acepta como entrada tanto una URL (`yt-dlp`) como un archivo local.
- [x] Con una URL, nunca descarga el directo completo: primero solo audio (`download_audio_only`) para el análisis, y video solo por el rango puntual de cada clip final ya decidido (`download_video_segment`).
- [x] Extrae audio mono 16 kHz vía `ffmpeg` para que el análisis no dependa del video completo.
- [x] Calcula una señal de energía (RMS, `librosa`) y una señal de aplausos/vítores, ambas sin ningún modelo de IA.
- [x] Fusiona ambas señales en una curva de interés, la suaviza y detecta picos locales.
- [x] Selecciona los `N` clips finales sin solape entre sí (NMS / `min_gap_seconds`).
- [x] Recorta cada clip con `ffmpeg`, reencuadre 9:16 por crop centrado, reencode de video + audio.
- [x] Genera `metadata.json` con timestamps, score, título (genérico en esta fase) y fuente de la señal, por clip.
- [x] Con `USE_AI_LAYER=false` (default), el pipeline corre de punta a punta sin ninguna llamada a un LLM ni a Whisper.
- [x] Un fallo puntual al descargar/renderizar un clip (ej. glitch transitorio de red) no aborta el resto de la corrida — se reintenta y, si sigue fallando, se omite ese clip y se sigue con los demás.
- [x] Cubierto por un test end-to-end real (`tests/test_pipeline_e2e.py::test_pipeline_end_to_end`), con `ffmpeg` real sobre un video sintético, sin red ni mocks de la etapa de señal/recorte.

### Fase 2 — Capa de IA opcional *(implementada, solo proveedor Gemini)*

**Criterios de aceptación:**
- [x] Flag `USE_AI_LAYER` apagado por defecto; con el flag apagado el comportamiento es idéntico a Fase 1 (ni Whisper ni el LLM se ejecutan).
- [x] Transcripción local con `faster-whisper`, condicionada estrictamente a `USE_AI_LAYER=true`.
- [x] Adaptador de LLM intercambiable (`llm/dispatcher.py` + diccionario de proveedores), con **Gemini** como único proveedor implementado (decisión explícita — Ollama, Claude, OpenAI y Groq quedan pendientes, ver más abajo).
- [x] El LLM reordena/filtra candidatos y genera título + razón por clip, sin reemplazar la selección sin-solape de Fase 1 (que sigue siendo una restricción física de renderizado, no delegable a texto generado).
- [x] Ante cualquier fallo de la capa de IA — sin API key, `google-genai`/`faster-whisper` no instalados, error de red, timeout, respuesta que no parsea como JSON válido, proveedor no soportado — el pipeline no lanza excepción ni aborta la corrida: cae de vuelta al comportamiento de Fase 1 (señal pura + título genérico) y deja un aviso por stderr.
- [x] Subtítulos quemados solo si hubo transcripción y `BURN_SUBTITLES=true`; si el burn-in falla (ej. `ffmpeg` sin `libass`), se reintenta automáticamente el mismo clip sin subtítulos en vez de perder el clip entero.
- [x] Cubierto por tests con la capa de IA mockeada — sin red, sin API key real, sin descargar modelos: `test_pipeline_end_to_end_with_ai_layer_mocked`, `test_pipeline_ai_ranking_with_subtitles_disabled`, `test_pipeline_falls_back_when_llm_raises` (`tests/test_pipeline_e2e.py`), más `tests/test_llm_adapter.py`, `tests/test_transcribe.py` y `tests/test_subtitles.py`.

**Pendiente dentro del alcance original de esta fase** (no bloquea el estado "implementada", que se definió explícitamente solo para Gemini): agregar Ollama y otros proveedores (Claude, OpenAI, Groq) al mismo adaptador — sección 4.3.

### Fase 3 — Publicación automática (TikTok + Instagram Reels) *(implementada)*

Cerrar el último tramo manual: subir los clips ya generados directamente a TikTok y/o Instagram Reels desde la línea de comandos, sin re-subirlos a mano por cada plataforma. Es un **comando separado y explícito** (`clipengine publish <plataforma>`), desacoplado de la generación de clips (`clipengine run`) — genera y publica siguen siendo dos pasos distintos, lo que da un punto de revisión natural (mirar los `.mp4` en `output_dir`) sin necesitar todavía la UI de la Fase 5.

La plataforma se elige de forma explícita y separada en cada corrida (`clipengine publish tiktok ...` o `clipengine publish instagram ...`); no existe un modo que publique en ambas a la vez en una sola invocación — para las dos, se corre el comando dos veces.

**Hechos de plataforma que condicionan el diseño** (verificados julio 2026):
- **TikTok** (Content Posting API): subida directa del archivo local en chunks, sin necesitar hosting público. Mientras la app no pase la auditoría de TikTok, **cualquier** post queda forzado a `SELF_ONLY` (privado) sin importar lo que pida el código — restricción de la plataforma, no un bug del pipeline.
- **Instagram** (Graph API, Reels): requiere cuenta Business/Creator vinculada a una Página de Facebook y una app de Meta (alcanza con modo Development + la cuenta como "Instagram Tester" para este caso de uso de una sola cuenta propia). Subida directa (resumable) también sin hosting público. A diferencia de TikTok, **publica de inmediato y en público — la API no tiene estado de borrador**.

**Criterios de aceptación:**
- [x] `clipengine publish` es un comando separado de `clipengine run`; correr `run` nunca dispara una publicación.
- [x] `clipengine publish` siempre requiere indicar una plataforma explícita (`tiktok` o `instagram`) como argumento; no existe un modo que publique en ambas dentro de la misma corrida.
- [x] Con `PUBLISH_TIKTOK=false` y `PUBLISH_INSTAGRAM=false` (default), `clipengine publish <plataforma>` no dispara ninguna llamada de red real, sea cual sea la plataforma pedida.
- [x] Adaptador por plataforma (`publish/tiktok.py`, `publish/instagram.py`) con la misma interfaz — agregar una plataforma nueva no requiere tocar el runner más que registrarla.
- [x] Subida directa del archivo local (chunked en TikTok, resumable en Instagram) — nunca requiere hosting público intermedio.
- [x] Autorización OAuth interactiva (`clipengine auth <plataforma>`) con protección CSRF (validación de `state`), y refresco automático de tokens en corridas no interactivas de `publish`.
- [x] Un fallo puntual en un clip (token vencido, red, rate limit, timeout de polling) nunca aborta el resto de la corrida.
- [x] Resultados registrados en `publish_status.json` (no en `metadata.json`, para no acoplar `run` y `publish`); correr `publish` dos veces no duplica posts salvo `--force`.
- [x] Documentado explícitamente que TikTok, sin auditar la app, publica en `SELF_ONLY` — no es un bug del pipeline.
- [x] Documentado explícitamente que Instagram publica de inmediato y en público, sin estado de borrador — de ahí `--dry-run`.
- [x] Cubierto por tests con HTTP completamente mockeado (sin red, sin credenciales reales, 51 tests nuevos en `tests/test_publish_*.py` + `tests/test_cli.py`), incluyendo que un clip fallido no bloquee los demás.

### Fase 4 — Seguimiento visual (reencuadre dinámico) *(no iniciada)*

Detectar y seguir a las personas en el plano (quién está hablando, el grupo completo) para mover el crop 9:16 dinámicamente según lo que ocurre en escena, en vez del crop centrado fijo de la Fase 1 — útil cuando el grupo/DJ no está centrado en el escenario.

**Criterios de aceptación (a cumplir antes de marcarla implementada):**
- [ ] El reencuadre dinámico es opcional (flag propio) y, si está apagado o falla, el pipeline cae al crop centrado de Fase 1 sin romperse — mismo principio que `USE_AI_LAYER`.
- [ ] Funciona sin depender de que la capa de IA generativa (Fase 2) esté activa.
- [ ] Cubierto por un test que verifique que el crop realmente se mueve entre frames cuando el sujeto no está centrado (no solo que el clip se genera).
- [ ] Documentado en el README con su propio flag y comportamiento de fallback.

### Fase 5 — Capa de revisión *(no iniciada)*

Interfaz en React/Supabase para ver los clips candidatos, sus scores/títulos, y aprobar/descartar antes de publicar.

**Criterios de aceptación (a cumplir antes de marcarla implementada):**
- [ ] Cada directo procesado genera un registro en Supabase con sus clips candidatos y su `metadata.json` asociado.
- [ ] La interfaz React permite listar los clips de una corrida, reproducirlos, y ver score/título/razón/fuente de señal.
- [ ] Permite aprobar o descartar cada clip individualmente antes de que se considere "publicable".
- [ ] No depende de que la Fase 2 (IA) esté activa — debe poder revisar corridas generadas solo con señal (títulos genéricos).

**En standby**: señal de chat (Twitch/YouTube) como fuente adicional de score (antes Fase 2) — se pospone porque el chat no es lo suficientemente activo en estos directos como para aportar una señal útil; se retoma si eso cambia.

---

## 9. Riesgos y limitaciones a tener en cuenta

- La detección de "mejores momentos" basada solo en energía de audio puede generar falsos positivos (ej. ruido fuerte que no es un buen momento musical) — hay que probar y ajustar los pesos del score con directos reales.
- El costo de la capa de IA (si se usa un proveedor de pago) depende del volumen de directos procesados; conviene medirlo con una prueba real antes de asumir que será insignificante.
- Las capas gratuitas de los proveedores en la nube (Gemini, Groq, Mistral) pueden cambiar sus límites o condiciones sin aviso — el diseño de adaptador intercambiable (sección 4.3) existe justamente para poder cambiar de proveedor sin fricción si eso ocurre.
- Si la privacidad del repertorio importa (por ejemplo, contenido no publicado aún), revisar las políticas de uso de datos de cada proveedor antes de activarlo — el modelo local vía Ollama es la única opción con garantía total de que nada sale del equipo.
- El chat como señal solo está disponible si la plataforma expone ese dato (no todos los directos lo tendrán).

---