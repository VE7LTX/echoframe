# EchoFrame
EchoFrame is a local personal research assistant tool designed to record and transcribe audio interactions, then integrate the results into a personal knowledge base.
EchoFrame Implementation Plan
System Overview
EchoFrame is a local personal research assistant tool designed to record and transcribe audio interactions, then integrate the results into a personal knowledge base. The system leverages a Zoom H2 Handy Recorder (used as a USB microphone) for high-quality audio capture, processes the audio entirely offline using state-of-the-art speech recognition (OpenAI Whisper) and optional speaker diarization (pyannote), and outputs structured markdown notes (with YAML metadata) suitable for an Obsidian vault. It also integrates with the Personal.ai API for advanced post-processing – such as generating summaries, tagging sentiment, or enabling question-answering on the transcripts – using the user’s personal AI model (with unlimited token usage). The focus is on developer clarity, modular design, and extensibility, ensuring each component (recording, transcription, diarization, AI integration, etc.) can be maintained or upgraded independently. This plan details how to implement EchoFrame as a local CLI or desktop application for personal use, highlighting file organization, workflow automation, and future extensibility.
User Requirements
EchoFrame’s implementation must meet the following key requirements (as derived from the user story):


Audio Input via Zoom H2: Utilize the Zoom H2 Handy Recorder as a USB microphone for audio input. The system should recognize the H2 as an input device and capture audio from it in real-time.


Local Audio Recording with Timestamps: Record audio sessions in high-quality WAV format, time-stamping the recordings (e.g. using filenames or metadata to capture date/time) and storing them on the local filesystem. Recording control should be simple (start/stop via CLI command or UI button).


Accurate Transcription (ASR): Perform local speech-to-text transcription on the recorded audio using OpenAI Whisper (or the optimized Faster-Whisper) to convert speech into text. The transcription should include timestamps for segments or words (for alignment and reference).


Speaker Diarization (Optional): When enabled, apply speaker diarization to the audio to distinguish different speakers in the transcript. This can be achieved via pyannote.audio or similar, so that the final transcript is labeled by speaker (e.g. Speaker A, Speaker B) with timing. This feature can be optional due to its computational cost.


Structured Output for Obsidian: Format the transcription outputs into a structured Markdown document with a YAML frontmatter header. The YAML metadata should include details like date, participants, tags, and other context, following conventions for the user’s Obsidian vault. The Markdown body will contain the timestamped transcript (segmented by speaker if applicable), and possibly AI-generated summaries or notes.


Personal.ai API Integration: Use the Personal.ai Developer API to enrich the notes after transcription. The user’s personal AI (with unlimited tokens) will be leveraged to generate summaries of the conversation, perform sentiment analysis (e.g. determine the overall sentiment or emotions of participants), and handle any Q&A prompts about the content. The system should upload transcripts to the Personal.ai “memory” and retrieve generated outputs to include in the Markdown or store for later queries.


Knowledge System Organization: The captured notes and AI annotations should integrate into the user’s personal knowledge system. EchoFrame should support workflows common in “Discovery Research”-style mixed-mode studies – e.g. handling interviews, phone calls, fieldwork observations, mystery shopping notes, internal meetings, cold-call notes, etc. Each note should be appropriately tagged or categorized (via YAML frontmatter or folder structure) so the user can easily browse or query by interaction type or project.


Local Installation and Reusability: Package EchoFrame as a convenient local tool. This could be a CLI utility (installable via pip or similar) or a desktop application. The installation should bundle or manage dependencies (audio I/O libraries, ML models, etc.), allowing the user to easily install and run the tool on their machine (without needing a cloud service). The solution should prioritize privacy (all sensitive data stays local except the optional calls to Personal.ai API) and be usable offline (transcription/diarization) with only the AI enrichment requiring internet.


These requirements emphasize a self-contained, extensible system that a developer or advanced user can rely on for capturing and organizing research conversations in a personal knowledge base. Next, we detail the design and implementation for each aspect of EchoFrame.
File + Folder Structure
A clear file and folder structure will ensure EchoFrame’s outputs are organized and easy to integrate into the Obsidian vault. We propose the following structure and naming conventions:


Base Directory: The user can designate a base folder (configurable) where EchoFrame will store all recordings and notes. This could be within the Obsidian vault (e.g. a folder named Research Audio) or a separate directory that the user later links to their vault. For example:


ObsidianVault/Research Audio/EchoFrame/




Audio Recordings: Within the base directory, have a subfolder (e.g. audio_raw/ or Recordings/) for raw audio files. Each recording file will be named with a timestamp and an optional short title. For example:
2026-01-12--Interview-with-ClientA.wav
The naming convention uses an ISO date (for chronological sorting) and a brief description of the session. The timestamp in the filename (and file metadata) serves as a record of when it was captured.


Transcripts/Notes: Another subfolder (e.g. transcripts/ or Notes/) will contain the Markdown files generated from each recording. We can mirror the audio filename for the note, but with a .md extension. For example:
2026-01-12--Interview-with-ClientA.md
This note will include YAML frontmatter and the transcript. Keeping the same base name as the audio file makes it easy to trace which audio file corresponds to which note.


Organization by Category (optional): To reflect Discovery Research-style categories, we could have subfolders by interaction type or project. For example:
EchoFrame/Interviews/2026-01-12--Interview-with-ClientA.md
EchoFrame/Fieldwork/2026-02-01--SiteObservation.md
EchoFrame/InternalSync/2026-02-05--TeamMeeting.md
This is optional and can be driven by metadata. The user might just use tags in YAML to label type, and keep all notes in one folder. However, a folder grouping by type or project can help manual browsing.


Config and Logs: It’s useful to have a configuration file, e.g. echoframe_config.yml in the base directory or user home, where settings like default device, personal.ai API key, default paths, model preferences (Whisper model size, diarization on/off) are stored. Also, a logs/ folder can capture runtime logs or errors for debugging.


Linking Audio to Notes: If desired, the audio file can be referenced in the Markdown note (e.g. via an Obsidian embed or a file link) so that the user can play back the original if needed. Alternatively, audio could remain outside the vault to save space, but linking ensures easy retrieval. Obsidian supports audio embeds, so a link like ![[2026-01-12--Interview-with-ClientA.wav]] could be included in the note (assuming the audio file is in the vault or a mounted folder).


This structure ensures that for every session, the user has a .wav file (raw data) and a corresponding .md file (processed knowledge). The naming conventions and YAML metadata (detailed below) allow easy search and filtering (for example, using Obsidian’s search or Dataview plugin queries). The approach is flexible: new categories can be added as needed, and the system should allow the user to configure naming or folder rules to fit their personal workflow.
Audio Handling and Capture
Capturing audio from the Zoom H2 is the first step. The Zoom H2, when connected via USB, can function as a standard audio interface (microphone) for the computer. EchoFrame will interface with it using a suitable audio library, focusing on cross-platform support and reliability:


Device Selection: The tool will enumerate audio input devices and allow the user to select the Zoom H2. The H2 typically appears as a USB audio input (sometimes offering 44.1 kHz stereo input). We’ll default to the H2 if detected, but also allow configuration in case the user has multiple devices.


Sampling Parameters: For high-quality transcription, record at 44.1 kHz or 48 kHz and 16-bit depth WAV (CD quality). The Zoom H2’s default is 44.1 kHz; we should ensure the system respects that or adjust accordingly to avoid resampling issues. (Notably, Windows may default the H2 to 48 kHz, so we’ll confirm or set the rate to match the device’s setting to avoid any audio distortion).


Mono vs Stereo: The H2 has multiple microphones (it can record in stereo or even 4-channel). For transcription purposes, a mono mixdown is sufficient (and sometimes preferable). We can record in stereo and later downmix to mono for processing, or record one channel. However, there is a potential use of stereo: if doing speaker diarization, a stereo recording of two people on separate channels could simplify distinguishing speakers, but in typical use the H2 will capture one mixed stream. We will proceed with mono audio for transcription unless a reason to keep stereo arises.


Recording Control: Implement a recording module that can start and stop recording based on user input:


In a CLI, a command like echoframe record --title "Interview with ClientA" can start capturing. The program would open the audio stream from the H2 and write to a WAV file on disk (using Python’s pyaudio or sounddevice). The user can stop with Ctrl+C or a specific keypress, upon which the file is finalized.


In a GUI (if an Electron/desktop version), a “Record” button toggles recording on/off. The UI can show a timer or levels.




Live Monitoring: Optionally, provide a way to monitor audio levels or recording duration in real-time to ensure the device is capturing correctly. At minimum, print status messages (e.g. “Recording… press Ctrl+C to stop” in CLI, or a red circle indicator in UI).


File Saving and Timestamp: When recording starts, note the current date-time. Use this to name the file (as described above) and also store the start time inside the file’s metadata or in the YAML of the note. The WAV file can include a LIST-INFO chunk for metadata, but since we’ll anyway log it externally, it may suffice to simply use filenames and note data. On stop, ensure the WAV header is properly written (file is not corrupted).


Recording Duration Limits: If needed, allow an optional max duration or auto-stop (for instance, if the user wants to record a fixed 30 minute session). Otherwise, it runs until manually stopped. If very long recordings are possible, we might also implement rolling files or buffering to disk continuously to avoid large memory use.


Silence Detection (Advanced): In future, a Voice Activity Detection (VAD) algorithm could be integrated to auto-pause or segment recordings when silence is detected. This can help in splitting meetings or skipping long silent periods. Initially, this is not required, but the design will leave room for adding a VAD-based trigger (perhaps to auto-stop recording after X minutes of silence or mark segments).


For implementation, we can rely on Python libraries:


sounddevice – a high-level library for capturing audio to NumPy arrays easily.


pyaudio – a widely-used PortAudio wrapper for more control (it reads raw audio frames and can write to WAV).
Either can work; python-sounddevice might allow simpler cross-platform usage and automatically yield NumPy data that we can directly pass to transcription if needed. We will record directly to file to avoid filling memory for long sessions. Using wave module in Python, we can incrementally write audio frames to a WAV file as they come in.


Developer considerations: We will implement the recording as a class or function that other components can call (so the CLI command and a GUI button can reuse it). We’ll handle exceptions (e.g. device not found, or input overflow errors) gracefully, prompting the user with clear messages (like “Unable to access Zoom H2 device – please check connection”). After recording, the module should return the path to the saved WAV file, along with metadata (start time, duration, maybe average levels if needed). This information will be used in subsequent steps (YAML frontmatter can include the duration or end time if desired).
Transcription Pipeline
Once an audio file is recorded, EchoFrame will automatically proceed to speech transcription. The pipeline will use OpenAI Whisper, which is known for its high accuracy on a variety of languages and noise conditions. For efficiency on local machines, we consider using Faster-Whisper (a CTranslate2-based Whisper implementation) which significantly improves speed and reduces memory usage while maintaining the same accuracy. The transcription pipeline includes the following steps:


Loading the Model: On initialization, EchoFrame will load the Whisper model (or a chosen variant/size). Model size can be user-configurable (tiny, base, small, medium, large). Larger models offer more accuracy, especially in noisy environments or for certain accents, but they are slower. If running on CPU, the user might prefer a smaller model or enable Faster-Whisper’s 8-bit quantization for speed. If a GPU is available, the large model can be used for best accuracy. We will autodetect hardware (CUDA or Metal on Mac) and allow overriding device settings.


Preprocessing Audio: Convert the recorded WAV into the format expected by the model. Whisper works on 16 kHz mono audio; if we recorded at 44.1 kHz, we will down-sample to 16 kHz (using an audio library like librosa or ffmpeg). If stereo, mix down to mono. Also, apply any needed normalization or noise reduction (Whisper is robust, so heavy preprocessing isn’t required beyond maybe trimming leading/trailing silence).


Transcription Execution: Run the Whisper model on the audio. Using HuggingFace Transformers pipeline or Faster-Whisper’s API, we will get the transcribed text and timestamps for segments. In a basic setting, Whisper returns a list of segments each with a start time, end time, and text. We will capture these. By configuring the pipeline with return_timestamps=True, we ensure timestamps are included. We might also set a word-level timestamps option if available (Whisper can output word timestamps in newer versions or via WhisperX).


Segmentation: Whisper automatically segments the output (usually at pauses or every few seconds). We might keep these segments as is for alignment with diarization, but for the final output, we’ll consider merging segments by speaker later (if diarization is used). We should also be mindful of Whisper’s built-in chunking: by default it processes 30-second chunks. Tools like WhisperX add custom VAD to segment properly, but we can rely on Whisper’s segmentation for now, or adjust parameters (e.g. using max_length or segment_length as available).


Accuracy Options: Provide options for language detection or specification (Whisper can auto-detect the language, but if the user knows the language of audio, we can pass a language code to possibly improve speed slightly). Also, allow enabling or disabling Whisper’s built-in temperature fallback and beam search parameters – these affect accuracy vs speed. We’ll default to Whisper’s recommendations for balanced performance.


Result Format: The output of transcription will be stored in an internal format, e.g. a list of segments: [(start_time, end_time, text), ...]. If diarization is off, we could merge all text into one block, but preserving segments with times is helpful for adding timestamps in the markdown and for later alignment if needed. Each segment may be a sentence or phrase. We will likely keep them for diarization alignment and then merge by speaker.


Using Faster-Whisper specifically: it is a reimplementation that uses a C++ backend and supports quantized inference, making it fast even on CPU. Installation is straightforward (pip install faster-whisper). We should ensure to handle model downloading (the first run will download the model weights). Those can be cached in the user’s home or a specified directory. We will document or manage the model cache (for example, downloading at install time or first use).
Progress and Feedback: Transcription of a long recording can take some time (e.g. a 1-hour audio might take a few minutes on a good GPU or significantly longer on CPU with a large model). The tool should give feedback – e.g., a progress bar or at least logs indicating that transcription is running. If using the Whisper API directly, we might not get granular progress, but we can output something like “Transcribing audio (~X minutes)...”. If using WhisperX or our own chunking, we can iterate and show progress per chunk.
After this step, we will have a raw transcript with timing information. If diarization is requested, we move to the next step; otherwise, we proceed to formatting the note.
Diarization Strategy
Speaker diarization will enable EchoFrame to label which speaker said which part of the transcript – crucial for interviews or meetings with multiple people. We mark this as optional because not all use-cases need it (e.g. a personal voice memo has only one speaker), and diarization can be resource-intensive. When enabled, the strategy is as follows:


Diarization Model: We will use the pyannote.audio toolkit, specifically a pre-trained speaker diarization pipeline (like pyannote/speaker-diarization@3.1). Pyannote is known for its accuracy in speaker detection and can be run locally with a pretrained model. Note that using pyannote’s pretrained models requires accepting its license and possibly a HuggingFace token for download. We’ll guide the user to provide this token in the config if needed.


Audio Segmentation for Speakers: The pyannote pipeline will take the WAV file and output a series of speaker-labeled time segments. For example, it might output: Speaker_0: [0s - 15.2s], Speaker_1: [15.2s - 30.5s], etc., meaning from 0–15.2 seconds Speaker_0 was talking, then Speaker_1 took over. It automatically determines the number of distinct speakers (though this can be configured or constrained if the user knows the number of speakers).


Aligning Transcripts with Speakers: The critical part is to align Whisper’s text segments with Pyannote’s speaker segments. We will implement or use an algorithm that goes through each transcription segment and finds which speaker’s time interval overlaps the most with that segment. In practice, this means for a given text segment (say from 10s to 14s, per Whisper), look at the diarization output and see whether that time window falls under Speaker_0 or Speaker_1 (or both). We choose the speaker with the greatest overlap duration. This temporal intersection approach has been documented as effective for combining ASR and diarization outputs. If a Whisper segment extends over a boundary of two speakers, we might split the text accordingly or assign it to whoever spoke majority of that duration. This is rare if Whisper segments are short.


Merging and Cleanup: Once each text segment has a speaker label, we can merge consecutive segments of the same speaker to improve readability. For instance, if Speaker_0 had two consecutive segments in the output (because Whisper might have split a long monologue into two), we join them into one segment for the final transcript to avoid choppiness. The alignment algorithm will handle these merges after initial labeling.


Speaker Naming: Pyannote will label speakers generically (Speaker_0, Speaker_1, etc.). We will expose a way for the user to map these to actual names if known. For example, if the YAML frontmatter has a field like participants: ["Alice", "Bob"], we can assume Speaker_0 is Alice and Speaker_1 is Bob (though we’d need to know which is which – perhaps assign in order of appearance or allow the user to specify). Initially, we might leave the generic labels in the transcript. The user can manually do a find/replace if desired or simply know from context. A stretch feature could be an interactive prompt after transcription: “Assign names to speakers? (Speaker_0 = Alice, Speaker_1 = Bob)”. For now, we document that the transcript will label speakers numerically and the YAML can list participants for clarity.


Integration with WhisperX (alternative): Instead of implementing alignment from scratch, we could leverage WhisperX, an open-source pipeline that combines Whisper transcription with VAD alignment and diarization automatically. WhisperX uses Faster-Whisper for ASR and pyannote for diarization under the hood, providing word-level timestamps and speaker labels as output. This is convenient – a single call can produce a speaker-annotated transcript – but it does require installing and running multiple models, making it heavier and a bit slower than doing transcription alone. Since we aim for extensibility, we can mention WhisperX integration as an option: for example, if a user sets diarization: true and has WhisperX available, just use WhisperX to get a rich output (with the caveat of needing the HuggingFace token for pyannote as noted). For clarity, the initial implementation can use the manual alignment (since we already parse Whisper output and can parse pyannote output).


Performance Considerations: Diarization will add overhead. Pyannote’s speaker model is fairly large (and usually requires GPU for realtime or faster processing). On CPU, it may be slow for long files. We should warn users that enabling diarization on, say, a 1-hour recording without a GPU could take significant time. The design could allow offloading this step (e.g., run diarization asynchronously or allow skipping if resources are constrained). But given this is a personal tool, the user can decide per use-case when they need speaker labels.


In summary, diarization enriches the transcripts by identifying “who spoke when”, which is invaluable for multi-speaker contexts. By combining Whisper’s transcription with Pyannote’s speaker segments, we achieve a detailed transcript segmented by speaker. This aligns with how professional transcription pipelines work, and ensures our Obsidian notes can clearly separate different voices in an interview or meeting. The methodology (temporal overlap matching and merging) is well-established and will be implemented in a maintainable way (likely a separate module/class SpeakerAligner that takes in transcripts and diarization result, similar to the approach described in published examples).
Personal.ai Integration
After generating the base transcript (and before or after saving the markdown note), EchoFrame will integrate with Personal.ai’s API to perform advanced post-processing. This step allows us to leverage a powerful AI model (tailored to the user’s own “AI persona”) to summarize and analyze the content, as well as make it queryable in the future. The integration consists of a few parts:


API Setup: The user will need to provide their Personal.ai API key and the DomainName of their AI model (each Personal AI persona has a unique domain identifier). These can be stored in the config file. We will use the API endpoints documented by Personal.ai:


Upload Document (POST /upload-text): to ingest the transcript into the user’s AI memory.


AI Message (POST /message): to ask the AI questions or give instructions and get responses (for summary, sentiment, etc.).




Uploading Transcripts to Memory: Once a transcript is ready (the text content of the conversation), we call the Upload Document API. We send the text, a title, time metadata, and tags in a JSON payload. For example:
{
  "Text": "<full transcript text>",
  "Title": "Interview with ClientA (2026-01-12)",
  "DomainName": "<user_domain>",
  "Starttime": "2026-01-12T20:15:00Z",
  "Endtime": "2026-01-12T21:00:00Z",
  "Tags": "Interview,ClientA,DiscoveryResearch",
  "is_stack": true
}

This will add the content to the user’s Personal AI “memory stack”. We include start/end times in ISO format, and tags like the interaction type or project name (mirroring what we put in YAML). The API should respond with a success message (e.g. “doc accepted and processing”). This means the AI is ingesting the text (tokenizing and indexing it into its knowledge base). This usually happens quickly (a matter of seconds for a few thousand words, depending on Personal.ai’s backend).


Post-Processing Queries: With the content in memory, we can now use the AI Message endpoint to get summaries or other analyses. Essentially, we’ll be “chatting” with the Personal AI through the API. The key is to craft prompts that yield the desired output:


Summary Generation: We can ask the AI for a summary of the conversation. For example, send a message: “Summarize the key points of the above conversation in a few sentences.” We might provide context like “Participants were talking about [topic].” or request a format (“bullet points” or “short paragraph”). The Personal AI will use the newly uploaded transcript in its memory to respond with a summary. We can also leverage the Events field of the API call to focus on the specific document by title. For instance, {"Text": "Give me a summary of the notes from the interview with ClientA on 2026-01-12.", "Events": "Interview with ClientA (2026-01-12)", ...}. Using Events (or specifying the Title as context) is akin to referencing that specific document in the AI’s memory for the query.


Sentiment Tagging: We can ask the AI to assess sentiment. This could be an overall sentiment (“What was the overall mood or sentiment of the conversation?”) or per speaker (“How did ClientA seem to feel about the project?”). The AI’s response can be parsed for a qualitative sentiment (e.g. “ClientA was mostly positive and enthusiastic, though with a moment of concern about timeline.”). We might simplify this into tags like sentiment: positive in YAML, or include a short note in the summary section. If a more structured sentiment score is needed, an alternate approach is to use a separate sentiment analysis tool on the text directly (like a local NLP model or another API), but since Personal.ai can understand context, it may give a richer answer (capturing emotions expressed).


Key Insights / Q&A: The integration allows the user (or the system) to query the content. For example, we could ask “What were the action items mentioned?” or “Extract any important numbers or dates mentioned in the call.” This goes into more exploratory QA. We likely won’t automate too many of these by default, but we ensure that the user can later ask their Personal AI these questions. (The user, via the Personal.ai app or via our tool’s CLI, could pose questions and get answers referencing the transcript, since it’s stored in memory.)




Inserting AI Responses into the Note: Once we get the AI-generated summary or tags, we incorporate them into the Markdown output:


The summary can be placed at the top of the note (either in the YAML frontmatter as a multi-line field, or as a Markdown section). For readability in Obsidian, we might prefer to put an “## Summary” section in the content. Alternatively, store it in YAML (using the > syntax for multi-line) under a key like summary – but YAML is usually hidden in preview, so having it in the content might be better for quick reading. We can do both: YAML for metadata queries, and visible section for reading.


Sentiment could be a YAML field (e.g. sentiment: "Positive" or a scale 1-5) and/or a note in the summary (e.g. “Overall, the conversation was positive.”). If multiple participants, we might list each in YAML like sentiment_client: positive, sentiment_user: neutral if we had that detail, but that may be overkill. A general sentiment is likely enough, unless the user specifically wants granular.


If the AI identifies action items or decisions, those could be added as a list in the note (perhaps under a “## Action Items” heading). This isn’t explicitly required, but the user’s mention of “Discovery research-style” and the known usage of transcripts suggests that highlighting follow-ups or insights is valuable. We could have the AI produce a brief list of “insights” or “next steps” if prompted. For example, after the summary, ask: “List any action items or next steps that were mentioned.” This can be a future add-on or configured via a flag.




Error Handling: If the Personal.ai API calls fail (network issues or API error), the system should not fail the whole note creation. We will catch exceptions and perhaps log a warning in the note like “(Summary generation failed at this time)” or simply proceed without the AI augmentation. Since it’s not core to getting the transcript, it can be retried later. The user could run a command like echoframe summarize <note> to retry or update the summary once connectivity is back.


Privacy Consideration: By design, the raw audio and initial transcription stay local. Only when we call the Personal.ai API do we send the text externally (to the Personal.ai cloud). The user has presumably agreed to that by providing the API key (and Personal.ai touts privacy of user data, treating it as the user’s own model). We will document this data flow so the user is aware. If the user prefers absolutely no cloud, they could skip this integration.


Overall, the Personal.ai integration adds a powerful “AI co-pilot” dimension to EchoFrame. By uploading text to the user’s personal AI model, the knowledge becomes queryable and summarizable on demand. It transforms raw transcripts into more useful insights, without the developer having to implement complex NLP locally. We just need to ensure the system is modular: e.g., a user with no Personal.ai account can disable this feature and still use everything else. Conversely, in the future, integration with other LLM services or local LLMs could be added as alternatives (maintaining extensibility).
Obsidian Output Formatting (Markdown + YAML)
The final output of EchoFrame for each session is a Markdown file tailored for Obsidian. We aim for a clean, structured note that can be easily read and also processed by Obsidian’s plugins (like Dataview for querying metadata). The formatting will be as follows:


YAML Frontmatter: At the very top of the file, we include YAML metadata enclosed in the triple-dashed lines. For example:
---
title: "Interview with ClientA"
date: 2026-01-12
time: "20:15"  # local start time of recording
duration: "45 min"
participants: ["Researcher - Alice", "ClientA - Bob"]
type: "Interview"
project: "Project X"
tags: ["DiscoveryResearch", "ClientA", "Interview"]
summary: > 
  ClientA was enthusiastic about the new design, asking many questions 
  about the timeline. Some concerns were raised about budget, but overall 
  the discussion was positive and several action items were identified.
sentiment: "Positive"
---

Let’s break down these fields:


title: A human-friendly title for the note. We can derive this from the recording title or user input (e.g. “Interview with ClientA”). If the user didn’t give a title, we can generate one from type + date or leave it as untitled date.


date and possibly time: The date of the interaction (we can use recording start timestamp). Time could be included if needed (for sorting or uniqueness, we have it in filename anyway). Obsidian can interpret date for daily note linking or timeline plugins.


duration: (optional) length of the recording. Not critical, but might be nice meta.


participants: A list of people or entities involved. We can fill this if the user provided names or after the fact. In the example, we label one as researcher and one as client for clarity. If names aren’t known, we might list generic “Speaker_0, Speaker_1” or just number of speakers. The user can edit this later. This field is useful for filtering notes by person.


type: Category of interaction (interview, meeting, fieldwork, etc.). Possibly set from user input or a command-line flag. This corresponds to the “Discovery research-style mixed modes” classification. Having this in YAML means the user can query “all interviews” easily.


project: If relevant, the project or context this belongs to (could also be encoded in tags or folder). This helps group related studies.


tags: A set of tags (Obsidian tag format or just in YAML list) to further categorize. E.g. we include a “DiscoveryResearch” tag to indicate this note came from the research workflow, plus specific ones like the client name, etc. These tags can be inline (with # in the content) or in YAML as shown. Both are fine; YAML tags might need a plugin to read, whereas inline tags are directly recognized by Obsidian. We could do both for safety: e.g. at bottom of note include #DiscoveryResearch #Interview #ClientA.


summary: Here we include the summary text provided by Personal.ai (or any summarization step). Using the YAML > block style keeps it as a single folded paragraph in YAML. Note: Obsidian’s core will not show this in the preview (since YAML is metadata), but we include it here so that the user (or plugins) can quickly grab the summary without parsing the whole transcript. It’s also stored within the note in case the user wants to extract or view it in edit mode.


sentiment: A short sentiment tag or descriptor. This could be just one of Positive/Negative/Neutral, or something like “Mixed” or “Informative” depending on context. We place it as a separate field for quick scanning (one could create a Dataview table of all interviews with sentiment, for instance).


The YAML frontmatter is extremely useful for data queries and organization in Obsidian. For example, the user can use the Dataview plugin to list all notes of type “Interview” and show participants or sentiments in a table. By storing this metadata consistently, we enable a more powerful PKM (personal knowledge management) workflow.


Main Content - Heading: After the YAML, we can have a title or heading for the note. Often the YAML title is enough, but we might still put a level-1 heading for visibility (Obsidian shows the filename as title by default though, so this is optional). For example:
# Interview with ClientA - Jan 12, 2026
This could combine title and date for clarity.


Summary Section: Next, if we want the summary visible in reading mode, we add:
## Summary
ClientA was enthusiastic about the new design... (the summary text here).
This duplicates what’s in YAML summary, but ensures that when viewing the note, the key points are immediately readable without digging into metadata. This is a user experience choice – many might appreciate seeing the summary at top. If the summary is very short, it could even just remain in YAML only. We can decide to include it in both places for completeness.


Content Sections: The core content will likely just be the Transcript, but we might structure it further:


## Transcript (or simply no heading, just start the dialogue). Under this, we list the conversation turns.


If there are any Action Items or Insights identified, we could have ## Action Items with a bullet list, or ## Key Takeaways. This would come from additional prompting of the AI or manual extraction. This is more in the “stretch goals” realm unless we find a straightforward way to parse for “TODO” or commitments in the text. We note it as a possibility.




Transcript Formatting: We list each speaker’s dialogue in chronological order, with timestamps:


Each entry starts with a timestamp (perhaps in [hh:mm:ss] format) and the speaker name, followed by a colon and the transcript text. For example:
[00:00:00] Alice: Thank you for meeting with me today.
[00:00:05] Bob: My pleasure. I’ve been looking forward to discussing the project.
We will format the speaker names in bold or otherwise to distinguish them. The timestamp is in square brackets. This format is easy to scan and one can visually align time progression. Also, if the user clicks an audio embed (if we included the audio file in the note), they might manually scrub to match these timestamps.


We will insert timestamps at the beginning of each speaker’s segment (which usually corresponds to each time they start talking). If a speaker monologue is long, we could break it into smaller chunks with intermediate timestamps (say every 30 seconds) for easier navigation, but that might clutter. It’s simplest to timestamp each turn.


The text will be the verbatim (or slightly cleaned) output from Whisper. We might perform light cleaning: e.g. ensure punctuation spacing is okay, maybe capitalize the first word of sentences if Whisper doesn’t. However, we should be careful not to alter content meaning. Also, filler words or transcription errors are part of the text – the user can edit the note later if needed. Our role is to capture accurately.


If diarization was off or there’s only one speaker, we can format it as a single monologue or paragraphs with timestamps at intervals.


For readability, we keep paragraphs short. If someone speaks a very long paragraph, it might appear as one block. We can consider breaking long segments by sentence or timestamp every ~1 minute even if speaker continues, to avoid a wall of text. The developer can implement a rule like “if segment text > N characters, consider splitting by sentence boundary and mark time”. But perhaps this scenario is rare in natural conversation (people pause).




Linking and References: If relevant, we can link to related notes. For example, if this is part of a project, we might put at the bottom “Related: [[Project X Notes]]” or if a participant has a bio note, link their name (e.g. [[Bob (ClientA)]]). This is manual unless we have data about participants. Possibly out of initial scope, but the user can easily add those links afterwards using Obsidian’s features.


Footer: Optionally, we could include a reference or signature like “Generated by EchoFrame on 2026-01-12” just so it’s clear the note was auto-generated (and maybe to find notes generated by the tool). But this might not be necessary and can be omitted for a cleaner look.


Images or Attachments: Not really applicable unless the user adds them. Our tool doesn’t inherently capture images (just audio). We won’t include any non-text except maybe the audio file link as mentioned earlier. Including the audio as an attachment within the vault (if user chooses) can be helpful – Obsidian can play it, and the transcript times allow manual sync.


The goal of this formatting is that when the user opens the note in Obsidian, they immediately see a concise summary, and then the full transcript with clear delineation of speakers and times. The YAML provides machine-readable context that the user can use to query or filter notes (for example, creating a table of all interviews with their dates and summaries using Dataview). We also ensure that the note is easy to skim – headings for Summary/Transcript break it up, short paragraphs per speaker turn, etc., aligning with the user’s request to avoid dense text.
Example snippet in final note (in rendered view):

Summary: ClientA expressed enthusiasm about the design, raised budget concerns, but overall positive. Key next step: schedule a follow-up to address budget.
Transcript:
[00:00:00] Alice: Thank you for meeting today.
[00:00:05] Bob: My pleasure. I’m excited to talk about the new project...
[00:00:15] Alice: (laughs) That’s great to hear...
... and so on.

This shows the structure we intend. In editing mode, the YAML would appear at top (hidden in preview), and the rest as shown.
CLI / Automation Workflow
EchoFrame is designed to be used either via a Command-Line Interface or a simple GUI. Here we outline the typical workflow from the user’s perspective (CLI variant for concreteness) and how the automation is handled under the hood:


User Initiates Recording: The user connects the Zoom H2 via USB and runs a command, for example:
$ echoframe record --title "ClientA Interview" --type Interview --participants "Alice (Researcher), Bob (ClientA)"

This command triggers the recording module. (If using a GUI, the user would maybe select a type from a dropdown, enter a title, and hit “Record”). The optional parameters provided (title, type, participants) will be used in the metadata. If not provided, EchoFrame can prompt for them or use defaults.


Recording Phase: The program prints a message like “Recording... (Press Ctrl+C to stop)”. Audio data from the H2 flows into the system. We write it to Recordings/2026-01-12--ClientA-Interview.wav. We continuously monitor for the stop signal.


Stop Recording: The user stops the recording (Ctrl+C or clicking Stop). EchoFrame closes the audio stream and finalizes the WAV file. It then prints something like “Recording saved: 2026-01-12--ClientA-Interview.wav (45.2 MB)”.


Transcription Phase: Immediately, EchoFrame transitions to processing:


It might show a message: “Transcribing audio with Whisper...”. If possible, a progress bar or spinner is shown. We could estimate progress if we chunk the audio (e.g. per minute processed).


The user waits while transcription happens. (If this is a GUI, maybe a progress bar fills, and we could show intermediate results if implementing streaming transcription – though initial version might just wait for completion).


Upon completion, we log “Transcription completed. (Approx X words)”.




Diarization Phase (if enabled): Next, if --diarize flag was given or config says so, we run diarization:


Show “Identifying speakers...”. This could similarly have updates (like percentage of audio processed by pyannote, if obtainable).


After diarization, log “Speaker separation completed (2 speakers identified).”.


Perform alignment of text with speakers.




AI Post-processing Phase: If Personal.ai integration is configured (API key present), proceed:


“Uploading notes to Personal AI...”.


Call upload API; on success (we can wait for the 200 OK), log “Uploaded to Personal AI memory.”.


Then “Generating summary via AI...”. We send the summary prompt and wait a moment for the response.


“Generating sentiment analysis via AI...”. Send sentiment prompt, etc.


These could be done in parallel if we want to speed up (two separate API calls simultaneously since they don’t depend on each other). But sequential is fine too.


Once responses are in, we incorporate them. Log “AI summary and tags received.” If something fails, warn “(AI request failed, skipping AI augmentation)”.




Note Assembly: Now all pieces are ready to assemble the Markdown note. The tool will create the .md file content:


Insert YAML (with provided title or generated one, participants, etc., plus the summary/sentiment if we have them).


Write the transcript in the described format. Ensure proper escaping of any special characters in Markdown (Whisper might output “#” or “*” literally if spoken; we should escape those to not break formatting).


Save the Markdown file in the specified folder.




Completion Output: The CLI prints a success message like:
Note created: EchoFrame/Interviews/2026-01-12--ClientA-Interview.md
Optionally, we could offer to open it directly in Obsidian (if we know the vault path and if Obsidian has a URI protocol set up). For example, on some OS, we could call obsidian://open?... with the file path to open it. Or simply inform the user to open Obsidian to view the note. In a GUI, we might have a button “View in Obsidian” if feasible.


Follow-up: If the user wants to later query the AI about the note, they can either go to Personal.ai’s interface or use an EchoFrame command. We could implement a CLI command such as:
$ echoframe ask "What were the main concerns discussed?" --event "ClientA Interview 2026-01-12"

The tool would call the AI Message API with that question focused on that event/note and print the answer. This turns the tool into a Q&A assistant for the stored knowledge. This is beyond the core flow, but an example of how the user could leverage the integration.


Throughout this workflow, the emphasis is on automation – the user should ideally do minimal manual steps beyond initiating the process. Recording to final note generation is one contiguous flow. However, each step should also be available as a separate command or module for flexibility. For instance, maybe the user already has an audio file (recorded externally) and just wants to transcribe it with EchoFrame – we could allow:
$ echoframe transcribe path/to/audio.wav [--diarize]

Similarly, a user might want to re-run summarization on an old note with updated AI – so a command
$ echoframe summarize path/to/note.md

could parse the note, upload to AI and update the summary. By separating concerns, the workflow can accommodate various use cases (but the primary is the seamless record-to-note pipeline).
We will implement the CLI using a library like Python’s argparse or click for nice subcommands. Each subcommand (record, transcribe, diarize, etc.) calls the underlying functions we described. Logging and verbosity can be controlled with flags (e.g. a -v for more detailed logs if debugging).
For an Electron or desktop app, the workflow is similar but with a UI: the user would click “Start” and “Stop”, then see progress indicators and finally get a notification “Note created”. Under the hood it calls the same logic. The CLI is easier to start with, and a GUI can be built on top of it once the core is stable.
Local Installation & Packaging Considerations
EchoFrame is intended for personal use, so installation should be as straightforward as possible for a developer or technically inclined user. Here are the considerations for packaging and installation:


Python Package: We will structure EchoFrame as a Python project that can be installed via pip (e.g. pip install echoframe). This means writing a setup.py or pyproject.toml with entry points for the CLI (so that the echoframe command is created on install). Dependencies will include:


Audio I/O libs: sounddevice or pyaudio, scipy (for writing WAV if using sounddevice’s numpy approach).


ASR libs: whisper (openai-whisper) or faster-whisper, plus PyTorch or TensorFlow backend as needed. If using faster-whisper, it brings its own CTranslate2 binary, but still might need PyTorch for WhisperX if we integrate that. We should pin compatible versions for reliability.


Diarization: pyannote.audio (which in turn requires PyTorch and other ML dependencies, plus a specific version due to model compatibility). We must note that pyannote is a heavy dependency; we might make it optional (install if user really wants diarization).


Personal.ai API: no official SDK is needed if we use requests to call the REST API. We just need to include that or use Python’s httpx/requests.


YAML handling: PyYAML to easily write YAML frontmatter.


If a GUI is to be packaged, we might not do that in Python directly but via Electron (so separate).




Platform compatibility: Ensure that any compiled dependencies are handled:


pyaudio often has issues installing via pip on certain systems. sounddevice might be easier since it uses PortAudio under the hood as well but maybe via CFFI. We might prefer sounddevice for simplicity (RealPython notes it records to numpy and can be saved easily).


GPU support: if the user has a GPU with CUDA, installing PyTorch with CUDA is the user’s responsibility (we can advise them to install torch before installing echoframe for GPU support). Alternatively, use pip extras like pip install echoframe[gpu] to include a torch with CUDA if possible. This gets complicated; likely, we’ll instruct in docs “if you want GPU acceleration, install PyTorch separately with the appropriate CUDA version”.


Whisper models: The first run will download the model weights (which can be hundreds of MB). We might provide a way to download during installation (e.g. if using openai-whisper, it downloads on first use; faster-whisper might do similarly or we can programmatically download the chosen model on setup).


For macOS users (with Apple Silicon), ensure that faster-whisper or whisper uses the correct backend (Metal support, etc.). This is often handled internally (whisper uses FFmpeg to load audio and can use Metal for compute if torch is on MPS device).


In summary, cross-platform audio recording is probably the trickiest. We will test on Windows, Mac, Linux with the H2 device if possible. We may include troubleshooting in docs (like if the device doesn’t work, instruct to check OS audio settings or try run as admin on Windows, etc.).




Standalone Executable: Some users might prefer an .exe or .app so they don’t have to manage Python and dependencies. We can consider using PyInstaller or cx_Freeze to bundle the Python program and all necessary libs into a single executable. This is feasible but the size might be large (especially including ML libraries and models). Perhaps a better approach is to distribute as a Docker container for those who are okay with that, but audio input from a USB mic inside Docker is non-trivial. So, a native app per OS might be better:


Windows: use PyInstaller to create echoframe.exe. It will include necessary .dlls. We have to test that audio and torch work inside it.


Mac: PyInstaller can create an .app bundle. Or since Mac users often are fine with Python/pip, they could use brew to install as well if we publish there.


Alternatively, since an Electron app was mentioned, one could create an Electron UI and package it with Node, and have the heavy lifting done by a Python backend. For example, the Electron app could call the CLI commands in a hidden way or communicate via an API. This is a more complex architecture (two runtimes), so might be a stretch goal. It would, however, give a nice user-friendly experience (like a window with a record button).


Another alternative is using a web interface (e.g. a minimal Flask app serving a local webpage that can control the recording and display output), then the user could run echoframe --serve and interact in their browser. This might be easier than Electron packaging and still cross-platform. But again, this is an optional front-end idea.




Installer/Environment: We should ensure that necessary external tools are present:


FFmpeg: Whisper or the HF pipeline may need FFmpeg to read the audio file. We should either bundle an FFmpeg or instruct the user to install it. Some Python libs use soundfile or pydub which rely on system encoders. Since we use WAV (uncompressed), we might not strictly need FFmpeg for encoding, but the Whisper model might spawn ffmpeg to downsample or to load various formats. We can include ffmpeg-python or just document that ffmpeg is required.


On Windows, if using PyAudio and not sounddevice, PyAudio requires a PortAudio library. Usually pip install pyaudio comes with the binary for Windows, but not always updated. sounddevice uses PortAudio built in via CFFI I think. We’ll lean to sounddevice to avoid that hassle.




Configuration: After installation, the user should create or edit the config file to add their Personal.ai API key and preferences. We can automate this: e.g. echoframe configure command that prompts for API key, default vault path, etc., and writes ~/.echoframe/config.yml. This reduces friction of manually editing.


Security: The API key should be stored safely (the config file should have proper permissions or we advise the user to not share it). The key will be read to set an HTTP header in requests. We won’t log the key anywhere. If using Electron, we must be careful not to expose it to the frontend JavaScript; it should stay in a backend process.


Updates: As a personal tool, we might not have frequent updates, but if distributing via pip, the user can update with pip. If via a packaged executable, they’d have to download a new release. We can incorporate a version check or just rely on user to pull latest if needed.


In essence, a pip-installable CLI tool is the primary distribution, with potential for an Electron-based UI wrapper if desired. This way, developers or technical users can get started quickly, and the system remains open and extensible (since it’s just Python code they can modify if needed). We will include documentation for installation and a troubleshooting section for common setup issues (especially around audio device and model downloads).
Future Features / Stretch Goals
While the above covers the core functionality, there are several opportunities to enhance EchoFrame further. These “stretch goals” could be tackled as future improvements:


Real-time Transcription: Instead of recording then transcribing, a future version could transcribe on-the-fly. As audio is captured, we could stream it into Whisper in small chunks and display interim text (like how some meeting software do live captions). This is challenging with Whisper’s architecture, but shorter chunks with Whisper tiny model could give near-real-time output, later refined by the large model. This would allow the user to see live notes or even have live captioning during a call.


Interactive Obsidian Plugin: Instead of (or in addition to) being an external tool that dumps notes into Obsidian, we could create an Obsidian plugin interface. For example, a plugin that exposes a “Record” button in Obsidian, and when clicked it uses EchoFrame’s backend to record and then automatically inserts the transcript into the current note. There is already community work in this direction (e.g. Obsidian Meeting Recorder or Note Companion plugins that record and transcribe). EchoFrame could integrate or draw inspiration from those, focusing on local processing and Personal.ai integration as differentiators.


Speaker Name Calibration: Improve diarization by allowing the user to train or specify speaker profiles. For instance, if the user frequently interviews the same people, EchoFrame could learn the voice embeddings for each person so next time it can label speakers by name automatically (using something like pyannote’s speaker embedding comparison).


Advanced NLP Annotations: Beyond summarization and sentiment, we could auto-extract:


Topics or Keywords – e.g. generate a list of keywords or key phrases discussed, to use as tags or for quick overview.


Action Items – using either Personal.ai prompt or a local regex/heuristics (e.g. sentences with “will” or “need to” might indicate tasks).


Entities – identify names, organizations, dates mentioned (NER - Named Entity Recognition), and perhaps hyperlink them to existing notes (if a person or topic is already a note in the vault, auto-link it). For example, if “Project Phoenix” is said and there’s a note on Project Phoenix, link it.


Emotion Analysis – deeper than sentiment, identifying moments of high emotion in the transcript.
Many of these could leverage the AI or other libraries. The Scalastic article mentioned how transcriptions can enable comprehensive analysis, including sentiment and more.




Multi-modal Integration: If the user also takes photos or videos during fieldwork, EchoFrame could be extended to handle those – e.g. capture an image and embed it in the note with some voice annotation. Or transcribe video files not just audio (the pipeline is similar if we extract audio from video).


Alternate ASR Models: Whisper is great, but there are faster lightweight models or services. Perhaps integrate with local Kaldi or Vosk model for low-power devices, or if online is acceptable, allow using an API like Google Speech-to-text for potentially faster or more domain-tuned transcription. Extensibility means we could swap out the transcription backend easily.


Better GUI/UX: If the tool proves useful, investing in a full GUI with an integrated audio waveform viewer, ability to play/pause and edit transcript within the app, etc., could be explored. For now, the focus is on generating notes for Obsidian, but one could imagine EchoFrame itself becoming a little “editor” where you can listen and correct transcript then push to Obsidian.


Mobile Support: As a stretch, consider mobile usage. Obsidian is on mobile and one might want to record interviews on a phone. Porting the core to Pythonista or a Swift/Kotlin reimplementation might be out of scope, but perhaps using the Personal.ai mobile capabilities or even a simple voice memo that later goes through EchoFrame on a desktop.


Continuous Discovery Integration: If following the Continuous Discovery framework (as the term discovery research hints), EchoFrame notes could integrate with a system of insight tagging. For example, each note could have a place to add “insights” which link to a higher-level insight database. This is more on the process side, but our structured notes with metadata make it feasible to build such a system (with Dataview or even external scripts).


Testing and Accuracy Enhancements: Over time, refine the transcription accuracy by perhaps fine-tuning Whisper on the user’s own recordings (if the user has accent or jargon that could be improved). Also, keep an eye on Whisper’s updates or new models (if OpenAI releases Whisper v2 or other open ASR). We should design the pipeline to allow easy switching to new models.


Open Source Community and Plugins: Encourage the community (or the user themselves, since it’s personal) to develop plugins or scripts around EchoFrame, for example, integration with calendar (auto-schedule recording sessions from calendar events), or sending summaries via email to meeting participants, etc., if this tool were to be generalized.


In conclusion, EchoFrame’s implementation plan provides a robust starting point for capturing and organizing spoken information into a personal knowledge management system. By focusing on local processing, open formats, and integration with an AI assistant, it ensures privacy, control, and deep personalization. The design is modular and extensible, meaning developers (or the user as developer of their own system) can evolve it with new features as technology and needs progress. With this foundation, the user will be able to seamlessly turn their real-world conversations and research activities into a richly linked, searchable knowledge repository in Obsidian – amplifying their ability to derive insights from all those interactions.
Sources:


Real Python – Playing and Recording Sound in Python (for audio capture techniques)


Modal Blog – Choosing between Whisper variants (on Faster-Whisper and WhisperX advantages)


Scalastic – Whisper and Pyannote: Ultimate Solution for Speech Transcription (on combining Whisper ASR with Pyannote diarization)


Scalastic – (on applications like sentiment analysis of transcripts)


Personal.ai Documentation – Upload Document API (for adding transcripts to Personal AI memory)


The Sweet Setup – Obsidian YAML and Dataview (demonstrating use of YAML metadata in Obsidian notes)

Sources
