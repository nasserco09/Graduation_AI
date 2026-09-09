# Graduation_AI

Hybrid AI-based visual search prototype for a graduation project.

The system allows users to upload an image of a fashion product, optionally select the target object manually or with AI assistance, and search for visually similar products from a local catalog.

---

## Current Features

- Image upload
- Full-image visual search
- Manual product selection:
  - Rectangle
  - Polygon
  - Free Draw / Lasso
- AI-assisted product selection using SAM2
- Positive selection points
- Negative exclusion points
- Interactive mask refinement
- Product cutout generation
- Visual similarity search using CLIP
- Fast vector similarity search using FAISS
- GPU acceleration with PyTorch and CUDA
- Local/offline model support

---

## Current AI Pipeline

```text
User Image
   ↓
Optional Product Selection
   ├── Manual Selection
   │   ├── Rectangle
   │   ├── Polygon
   │   └── Free Draw
   │
   └── AI Assisted Selection
       └── SAM2
            ↓
        Product Mask
            ↓
        Product Cutout
            ↓
CLIP Image Encoder
   ↓
Embedding Vector
   ↓
FAISS Index
   ↓
Similar Products