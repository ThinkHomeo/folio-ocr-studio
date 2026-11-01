# Optional format-aware OCR models

Text OCR does not need model files. For the TPB 1891 format-aware profile,
copy trusted `mlp_model.pkl` and `shape_model.pkl` files into this folder,
or start Folio with `--models PATH`.

Models and generated research outputs are excluded from Git and the source
archive. The setup screen reports missing models and their expected location.
These custom models have no configured public download URL. Pickle models
must come from a trusted source and match the installed library versions.
