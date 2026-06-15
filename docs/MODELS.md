# 사용 모델

각 유닛마다 다른 LLM을 배정해서, 모델 고유의 톤이 곧 캐릭터가 되는 구조입니다.
이 프로젝트는 모델 가중치를 포함하지 않습니다. 아래 목록을 본인 Ollama에 `ollama pull`로 받아 사용하세요.

## 한국어 특화 (강력 추천)

| 모델 | 크기 | 출처 | pull 명령 |
|------|------|------|-----------|
| `eeve:10.8b` | 6.5GB | 야놀자 EEVE-Korean-Instruct | `ollama pull huggingface.co/QuantFactory/EEVE-Korean-Instruct-10.8B-v1.0-GGUF:Q4_K_M`<br>그리고 `ollama cp ... eeve:10.8b` |
| `gukbap:7b` | 4.7GB | Markr-AI Gukbap (7B 한국 SOTA) | `ollama pull huggingface.co/mradermacher/Gukbap-Qwen2.5-7B-GGUF:Q4_K_M`<br>그리고 `ollama cp ... gukbap:7b` |
| `bllossom:8b` | 4.9GB | MLP-KTLim Bllossom (Llama 한국어 튜닝) | `ollama pull huggingface.co/mradermacher/llama-3-Korean-Bllossom-8B-GGUF:Q4_K_M`<br>그리고 `ollama cp ... bllossom:8b` |
| `exaone3.5:7.8b` | 4.8GB | LG AI Research EXAONE 3.5 | `ollama pull exaone3.5:7.8b` |

## 다국어 / 일반

| 모델 | 크기 | 출처 | pull 명령 |
|------|------|------|-----------|
| `aya-expanse:8b` | 5.1GB | Cohere Aya (23개 언어) | `ollama pull aya-expanse:8b` |
| `glm4:9b` | 5.5GB | Zhipu (Tsinghua) | `ollama pull glm4:9b` |
| `mistral:7b` | 4.4GB | Mistral 7B Instruct | `ollama pull mistral:7b` |
| `llama3.1:8b` | 4.9GB | Meta Llama 3.1 | `ollama pull llama3.1:8b` |
| `dolphin3:8b` | 4.9GB | Eric Hartford Dolphin (검열 약함) | `ollama pull dolphin3:8b` |
| `granite3.3:8b` | 4.9GB | IBM Granite 3.3 | `ollama pull granite3.3:8b` |
| `falcon3:7b` | 4.6GB | UAE TII Falcon 3 | `ollama pull falcon3:7b` |
| `openchat:7b` | 4.1GB | OpenChat (친근 톤) | `ollama pull openchat:7b` |

## 라이선스 메모

- **Meta Llama 3 / 3.1 / 3.2**: Llama 3 Community License (재배포 제한 있음)
- **Google Gemma**: Gemma Terms of Use
- **Mistral**: Apache 2.0
- **Qwen / Qwen2.5**: Apache 2.0
- **EXAONE**: EXAONE AI Model License (연구/평가용 OK, 상업 제한)
- **Aya**: CC-BY-NC 4.0 (비상업)
- **GLM-4**: 자체 라이선스 (학술/상업 모두 OK with 조건)
- **EEVE / Bllossom / Gukbap**: 베이스 모델 라이선스 상속

상업 용도면 각 모델 페이지에서 라이선스 직접 확인 필요.

## 게이트(인증) 걸린 모델 받는 법

일부 GGUF 리포는 HuggingFace 로그인이 필요합니다 (401 에러).

1. 해당 모델 페이지에서 라이선스 동의 클릭
2. https://huggingface.co/settings/tokens 에서 Read 권한 토큰 발급
3. 환경변수 설정 후 Ollama 재시작:
   ```
   set HF_TOKEN=hf_xxxxxxxx
   ```
4. 다시 `ollama pull ...`

회피하려면 위 표처럼 `mradermacher` / `QuantFactory` / `bartowski` 같은 커뮤니티 재양자화 미러를 사용.

## 권장 7명 라인업 (한국어 페르소나 마피아)

1. `eeve:10.8b` — 안정적인 한국어
2. `gukbap:7b` — 가볍고 한국어 좋음
3. `bllossom:8b` — Llama 베이스 한국어
4. `exaone3.5:7.8b` — LG 톤
5. `aya-expanse:8b` — 다국어 안정
6. `mistral:7b` — 직설적
7. `dolphin3:8b` — 검열 약해서 마피아 적극적

VRAM이 충분하면 (24GB+) 위 모든 모델이 한 번 로드 후 게임 끝까지 상주.
부족하면 Ollama가 호출마다 모델 스왑하면서 진행됨 (호출당 몇 초 추가).
