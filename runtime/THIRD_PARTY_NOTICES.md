# Third-party runtime resources

The release preserves the selected upstream checkpoints and preprocessing/tokenizer files without changing their tensor contents. The original model cards are included beside the weights. This notice does not relicense any third-party work.

| Resource | Upstream source | Declared license |
| --- | --- | --- |
| SigLIP2 Base patch16 224 | https://huggingface.co/google/siglip2-base-patch16-224 | Apache License 2.0 |
| SAM2.1 Hiera Base Plus | https://huggingface.co/facebook/sam2.1-hiera-base-plus | Apache License 2.0 |
| Clothing dataset small, train subset | https://github.com/alexeygrigorev/clothing-dataset-small | CC0 1.0 |

The model license text is in `runtime/licenses/APACHE-2.0.txt`. The dataset's original license is included at `datasets/clothing_small/LICENSE`, with a copy in `runtime/licenses/CC0-1.0.txt`. Its original README is also included. Upstream author names, papers, and use information remain in the corresponding model and dataset cards.

Neural-model sources and publications:

- Michael Tschannen et al., *SigLIP 2: Multilingual Vision-Language Encoders with Improved Semantic Understanding, Localization, and Dense Features*, 2025. https://arxiv.org/abs/2502.14786
- Nikhila Ravi et al., *SAM 2: Segment Anything in Images and Videos*, 2024. https://arxiv.org/abs/2408.00714

The project's FAISS index and metadata are distributed with the original training-gallery images. The package does not include personal account databases, uploaded user products, telemetry, or experimental model checkpoints. Frontend vendor notices are retained in the frontend asset folders. Python dependencies are installed by the setup command; their distributions retain their own licenses.
