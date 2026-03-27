# Motif Scanner

Find the most common network motifs in all model instances within a specified directory.

## Usage

1. Add the environment variable `FANMOD_PLUS_PATH` pointing to your [FANMODPlus](https://github.com/zaritskylab/FANMODPlus/tree/main) binary:

```console
export FANMOD_PLUS_PATH="<path_to_binary>"
```

2. Run the evaluation script:

```console
motif_scan.sh <language_path> <model_directory> <output_directory>
```

## Restrictions

FANMODPlus can handle network motifs of size 3-8. The maximum vertex color is 128 _if edge colors are disabled_ (regardless of motif size). With edge colors enabled, the restrictions in the table below holds.

| Motif size | Max vertex colors | Max edge colors |
| ---------- | ----------------- | --------------- |
| 3          | 15                | 7               |
| 4          | 15                | 7               |
| 5          | 7                 | 3               |
| 6          | 0                 | 3               |
| 7          | 0                 | 1               |
| 8          | 0                 | 1               |
