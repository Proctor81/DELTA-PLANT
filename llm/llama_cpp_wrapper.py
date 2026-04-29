# Wrapper Python per llama.cpp (TinyLlama)
# TODO: Implementazione streaming e gestione processi

class LlamaCppWrapper:
    def __init__(self, model_path, context_window=2048, max_tokens=128, timeout=20):
        self.model_path = model_path
        self.context_window = context_window
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(self, prompt, stream=False):
        """
        Esegue llama.cpp con il prompt fornito.
        Se stream=True, restituisce un generatore di token.
        """
        import subprocess
        llama_bin = "./llama.cpp/build/bin/llama-cli"
        cmd = [
            llama_bin,
            "-m", self.model_path,
            "-n", str(self.max_tokens),
            "-p", prompt,
            "--ctx-size", str(self.context_window),
            "-no-cnv",              # disabilita modalità conversazione/interattiva
            "--single-turn",        # esci dopo una singola generazione (non entra in loop)
            "--log-disable",        # sopprime banner e messaggi di log su stderr
            "--no-display-prompt",  # non ristampa il prompt sull'output
        ]
        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # sopprime banner/stderr
                stdin=subprocess.DEVNULL,   # impedisce che llama-cli erediti stdin del terminale
                text=True,
                start_new_session=True,     # stacca dal terminale di controllo (impedisce scrittura su /dev/tty)
            )
            for line in proc.stdout:
                stripped = line.strip()
                # Filtra linee vuote, banner e prompt interattivi
                if not stripped or stripped.startswith("build") or stripped.startswith("model") or stripped == ">":
                    continue
                yield stripped
            proc.stdout.close()
            proc.wait(timeout=self.timeout)
        except Exception as e:
            yield f"[ERRORE llama.cpp] {e}"
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()

if __name__ == "__main__":
    model_path = "models/tinyllama-1.1b-chat-v1.0-q4_K_M.gguf"
    llm = LlamaCppWrapper(model_path)
    while True:
        prompt = input("human: ")
        if prompt.strip().lower() in ("exit", "quit", "esci"): break
        print("Prompt:", prompt)
        for token in llm.generate(prompt):
            print("DELTA:", token)
