### TARS-AI 2.0 Development Branch Update

The TARS-AI 2.0 development branch introduces several enhancements over the initial 1.0 release, including:

---

#### :rocket: **Core Additions**  

**Speech-to-Text (STT) Enhancements:**  
- Integrated **Whisper** for local STT alongside **Vosk** and external server options.  
- Added STT sensitivity configuration for improved accuracy.  
- Comprehensive improvements to the STT system for better transcription.  
- Significant speed improvements.  
- Dynamic microphone quality selection based on hardware.  

**Character Customizations:**  
- Persistent personality settings (e.g., humor and tone) for dynamic character interaction.  
- Expanded character settings and behavior customization options.  

**Function Calling:**  
- Dual methods for function calls: **Naive Bayes (NB)** and **LLM-based approaches**.  

**Voice-Controlled Movement:**  
- Enabled voice commands to control robotic movements with precise mapping.  

**Image Generation:**  
- Integrated **DALL·E** and **Stable Diffusion** for AI-powered image creation.  

**Volume Control:**  
- Fine-tuned volume adjustments through both voice commands and external configurations. **Credit: @mskull**  

**Home Assistant Integration:**  
- Seamless connection with smart home systems.  

---

#### :gear: **Technical Improvements**

- **Reworked LLM function** into its own module.  
- **Reworked LLM function** to be compatible with thinking models (Deepseek R1).  
- **Reworked build prompt function** for easy importing.  
- **Reworked memory module** to ensure correct prompt and memory management.  
- **Reworked tokenization** for proper counts.  
- **Renamed STL files** for better readability.  
- **Many fixes and tweaks** for better usability.  
- Over **196 commits**.  

**Override Encoding Model:**  
- Enhanced compatibility with models using `override_encoding_model`.  

**TTS Fixes:**  
- Resolved issues with special characters in Text-to-Speech.  

---