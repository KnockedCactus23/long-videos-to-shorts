# Propuesta de implementación: pipeline propio de recorte de clips para directos musicales

## 1. Objetivo

Construir un sistema propio, gratuito en su núcleo, que reciba un directo musical de ~1 hora (link o archivo) y produzca automáticamente varios clips verticales (9:16) listos para TikTok/Reels/Shorts — replicando lo que hacen OpusClip/Vizard/Klap, pero adaptado a contenido musical (algo que esas herramientas comerciales no cubren bien) y sin costos de suscripción.

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
 │  a) Energía de audio         b) Chat / clips de      │
 │     (librosa, siempre activo)   plataforma           │
 │                                  (si hay datos)       │
 │                                                       │
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
- Link de YouTube/Twitch → descarga con `yt-dlp`.
- Archivo local → se usa directamente.
- Si el directo fue en Twitch/YouTube Live, se descarga también el **replay del chat** (mensajes con timestamp) cuando esté disponible — es una señal gratuita y valiosa que se usa más adelante.

### 3.2 Extracción de audio
- `ffmpeg` separa el audio del video (mono, 16 kHz) para que el análisis no tenga que cargar el video completo. Es rápido y no requiere GPU.

### 3.3 Análisis de señales (motor de detección de momentos)
Tres fuentes de señal, diseñadas para funcionar de forma independiente:

| Señal | Herramienta | ¿Requiere IA generativa? | ¿Siempre disponible? |
|---|---|---|---|
| Energía de audio (picos RMS, aplausos/vítores) | `librosa` + clasificador de eventos de audio (YAMNet/PANNs, gratuitos, corren local) | No | Sí, siempre |
| Chat / clips ya creados por la audiencia | API de Twitch/YouTube | No | Solo si el directo tuvo chat público |
| Transcripción + razonamiento contextual | `faster-whisper` (gratis, local) + **LLM configurable** (opcional) | Sí, la parte de razonamiento | Solo si se activa la opción de IA |

### 3.4 Fusión y selección
- Las señales sin IA (energía + chat) se normalizan y se combinan en una sola curva de "interés" por segundo. Los picos locales de esa curva son los clips candidatos — esto **ya funciona sin gastar un centavo en IA**.
- Si la capa de IA está activada, el LLM configurado recibe la transcripción + los timestamps de los picos ya detectados, y:
  - Reordena/filtra los candidatos usando el contexto (ej. "la banda anuncia que toca su tema más conocido").
  - Genera un título/hook sugerido para cada clip.
  - Da una breve razón de por qué ese momento es interesante (similar al "Virality Score" de OpusClip, pero explicado en texto).
- Si la capa de IA está desactivada, el sistema simplemente ordena los candidatos por el score de energía/chat y genera un título genérico (ej. "Momento destacado 1", con el timestamp).

### 3.5 Recorte con FFmpeg
- Corte del segmento (`-ss` / `-to`, reencodeado para precisión de frame).
- Reencuadre a 9:16 — crop centrado por defecto (más simple y confiable para música que el seguimiento de rostro, que no aplica bien a un escenario/DJ set).
- Subtítulos quemados en el video **solo si hubo transcripción** (es decir, solo si la capa de IA/Whisper estuvo activa y hay partes habladas).

### 3.6 Salida
- Clips en `.mp4`, formato 9:16.
- Un archivo JSON con metadata de cada clip (inicio, fin, score, título, fuente de la señal que lo generó) para que la capa de revisión (React/Supabase) pueda mostrarlos antes de publicar.

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

---

## 5. Diseño para que la IA sea opcional

Esto se resuelve con un flag de configuración, independiente de qué proveedor se elija:

```
USE_AI_LAYER = true | false
LLM_PROVIDER = "gemini" | "groq" | "ollama" | "openai" | "claude"   # solo relevante si USE_AI_LAYER=true
```

| | `USE_AI_LAYER=false` (por defecto, gratis) | `USE_AI_LAYER=true` (requiere configurar un proveedor) |
|---|---|---|
| Selección de momentos | Solo señal (energía + chat) | Señal + razonamiento del LLM sobre la transcripción |
| Títulos de los clips | Genéricos (timestamp) | Generados con contexto ("hook" sugerido) |
| Subtítulos | No (no hay transcripción) | Sí, quemados desde la transcripción de Whisper |
| Costo adicional | $0 | $0 a centavos por directo, según el proveedor elegido (ver sección 4.2) |
| Requiere | Solo librerías locales | Una API key (o Ollama instalado localmente) |

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
- Su lógica de selección de momentos, orientada a diálogo — se reemplaza por el motor de señales musicales (energía, aplausos, chat) descrito en la sección 3.3.
- Su reencuadre por seguimiento de rostro — se reemplaza por un crop centrado, más adecuado para un escenario o set de DJ.

---

## 7. Stack técnico propuesto

- **Worker de análisis y recorte**: Python (`yt-dlp`, `librosa`, `faster-whisper` opcional, `ffmpeg` vía `subprocess`, más un adaptador de LLM intercambiable — SDK oficial del proveedor elegido, o cliente HTTP local si se usa Ollama).
- **Orquestación / metadata / revisión**: Node.js + Supabase, siguiendo el mismo patrón que ya usas para tu librería de clips — cada directo procesado genera un registro con sus clips candidatos, y una interfaz en React para revisar/aprobar antes de publicar.
- **Salida**: archivos `.mp4` en almacenamiento (local o Supabase Storage) + tabla de metadata en Supabase.

---

## 8. Fases de implementación sugeridas

1. **Fase 1 — Núcleo sin IA** *(implementada)*: entrada, extracción de audio, análisis de energía/aplausos, fusión, recorte con FFmpeg, salida. Funciona de punta a punta sin ninguna llamada a un LLM.
2. **Fase 2 — Capa de IA opcional** *(próxima fase a implementar)*: agregar Whisper + el adaptador de LLM (empezando por Gemini Flash y/o un modelo local vía Ollama, ver sección 4.2) detrás del flag `USE_AI_LAYER`, con generación de títulos/hooks y subtítulos. Otros proveedores (Claude, OpenAI, Groq) se agregan como opciones adicionales del mismo adaptador, sin cambiar el resto del sistema.
3. **Fase 3 — Seguimiento visual (reencuadre dinámico)**: detectar y seguir a las personas en el plano (quién está hablando, el grupo completo) para mover el crop 9:16 dinámicamente según lo que ocurre en escena, en vez del crop centrado fijo de la Fase 1 — útil cuando el grupo/DJ no está centrado en el escenario.
4. **Fase 4 — Capa de revisión**: interfaz en React/Supabase para ver los clips candidatos, sus scores/títulos, y aprobar/descartar antes de publicar.

**En standby**: señal de chat (Twitch/YouTube) como fuente adicional de score (antes Fase 2) — se pospone porque el chat no es lo suficientemente activo en estos directos como para aportar una señal útil; se retoma si eso cambia.

---

## 9. Riesgos y limitaciones a tener en cuenta

- La detección de "mejores momentos" basada solo en energía de audio puede generar falsos positivos (ej. ruido fuerte que no es un buen momento musical) — hay que probar y ajustar los pesos del score con directos reales.
- El costo de la capa de IA (si se usa un proveedor de pago) depende del volumen de directos procesados; conviene medirlo con una prueba real antes de asumir que será insignificante.
- Las capas gratuitas de los proveedores en la nube (Gemini, Groq, Mistral) pueden cambiar sus límites o condiciones sin aviso — el diseño de adaptador intercambiable (sección 4.3) existe justamente para poder cambiar de proveedor sin fricción si eso ocurre.
- Si la privacidad del repertorio importa (por ejemplo, contenido no publicado aún), revisar las políticas de uso de datos de cada proveedor antes de activarlo — el modelo local vía Ollama es la única opción con garantía total de que nada sale del equipo.
- El chat como señal solo está disponible si la plataforma expone ese dato (no todos los directos lo tendrán).

---