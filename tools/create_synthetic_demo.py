"""Create a deterministic, shareable demo without experimental input files."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from plstudio.data import parse_spectrum, save_project
from plstudio.plotting import DEFAULT_STYLE


def main():
    spectra = []
    x = np.linspace(730, 880, 351)
    rng = np.random.default_rng(42)
    for i in range(4):
        y = 100 + (1000 + 100*i)*np.exp(-0.5*((x-800-i*2)/(9+i))**2) + rng.normal(0, 2, x.size)
        raw = "\n".join(f"{xx:.8f}\t{yy:.8f}" for xx, yy in zip(x, y)).encode("utf-8")
        s = parse_spectrum(raw, f"Synthetic_{i+1}.txt")
        s.notes = "Synthetic Gaussian spectrum for software demonstration only."
        s.condition = str(20 + 20*i)
        spectra.append(s)
    output = Path(__file__).resolve().parent.parent / "examples" / "PL_synthetic_demo.plproj"
    output.parent.mkdir(exist_ok=True)
    save_project(output, spectra, DEFAULT_STYLE)
    print(output)


if __name__ == "__main__":
    main()
