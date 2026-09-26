"""Train (or reuse) the ETA and surplus models so their files ship with the deployment.

  cd backend && python -m scripts.build_models

Run as the Vercel build command (backend/vercel.json): Vercel functions have a read-only
disk, and training the ETA model takes about 20 seconds, so no request should ever train.
A model file saved by another scikit-learn version is retrained. Exits non-zero if a
model file is missing afterwards, so a bad build fails instead of deploying.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.intelligence.eta import model as eta_model  # noqa: E402
from app.intelligence.eta import train as eta_train  # noqa: E402
from app.intelligence.ml import model as surplus_model  # noqa: E402
from app.intelligence.ml import train as surplus_train  # noqa: E402


def main() -> None:
    for name, ensure, path in (("ETA", eta_model.ensure_eta_model, eta_train.model_path()),
                               ("surplus", surplus_model.ensure_model, surplus_train.model_path())):
        bundle = ensure()
        if not path.exists():
            raise SystemExit(f"{name} model was not saved to {path}")
        print(f"{name} model ready: {path} ({path.stat().st_size // 1024} KB, trained {bundle['trained_at']}, "
              f"scikit-learn {bundle['sklearn_version']})")


if __name__ == "__main__":
    main()
