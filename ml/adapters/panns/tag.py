"""Tag an audio file with PANNs (AudioSet) in fixed windows; print top labels per window and overall."""
import sys
import librosa
import numpy as np
from panns_inference import AudioTagging, labels

path, win = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
y, _ = librosa.load(path, sr=32000, mono=True)
at = AudioTagging(checkpoint_path=None, device="cpu")
n = int(win * 32000)
chunks = [y[i:i + n] for i in range(0, len(y) - n // 2, n)]
probs = []
for k, c in enumerate(chunks):
    c = np.pad(c, (0, n - len(c)))
    p, _ = at.inference(c[None, :])
    probs.append(p[0])
    top = np.argsort(-p[0])[:6]
    print(f"{k * win:6.0f}s  " + ", ".join(f"{labels[i]} {p[0][i]:.2f}" for i in top))
mean = np.mean(probs, axis=0)
print("OVERALL: " + ", ".join(f"{labels[i]} {mean[i]:.2f}" for i in np.argsort(-mean)[:15]))
