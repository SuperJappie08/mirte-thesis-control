# Figure/Data generation scripts
This folder contains scripts to regenerate the data and figures for my thesis.

These scripts assume that everything is contained in a `thesis` folder. (Not all of therese are a strict requirement, however it was only tested with this configuration)
This `thesis` folder should have the following file structure:

<!-- https://tree.nathanfriend.com/?s=(%27options!(%27fancy!true~fullPathF~trailingSlashF~rootDotF)~I(%27I%27thesiENths_wENmeasurementE06A-1C06AL08BG36B-1CO6BLNfigureRQ4OH08B5HNplot-KRmergeJQ40H%27)~version!%271%27)*79907933-%20493K*93HOML5G3rebuildJ6data-folder-7%5Cn%208setup-9%20%20C%2FHEs%2FF!falseG%2F*H...Isource!J.bashOKconfigL-2CM8AN73O*3QM-1GRE0M5%01RQONMLKJIHGFEC98765430* -->
```
thesis/
├── ths_ws/ (ROS workspace can have anyname)
├── measurements/ (Location of the data can be different)
│   ├── data-folder-A-1/...
│   ├── data-folder-A-2/...
│   └── setup-B/
│       ├── data-folder-B-1/...
│       └── data-folder-B-2/...
├── figures/ (This folder contains the figures and tex-data)
│   ├── setup-A/ (This setup uses a merged plot-config)
│   │   ├── rebuild.bash (This must be rebuild-figures-config.bash)
│   │   ├── setup-A-1/
│   │   │   ├── config
│   │   │   └── ...
│   │   ├── setup-A-2/...
│   │   └── ...
│   └── setup-B/ (This setup does not use a plot-config)
│   |   ├── rebuild.bash (This must be rebuild-figures-no-config.bash)
│   |   └── ...
│   └── ...
└── plot-configs/ (This folder will contain bounds matching for the figures)
    ├── setup-A/
    │   ├── rebuild.bash (This must be rebuild-plot-configs.bash)
    │   ├── merge.bash (This must be merge-plot-configs.bash)
    │   ├── setup-A-1/
    │   │   ├── config
    │   │   └── ...
    │   └── setup-A-2/...
    └── ...
```

## Figures
**TODO: Finish instructions**

## Plot-configs
**TODO: Finish instructions**
