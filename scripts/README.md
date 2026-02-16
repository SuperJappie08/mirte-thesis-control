# Figure/Data generation scripts
This folder contains scripts to regenerate the data and figures for my thesis.

These scripts assume that everything is contained in a `thesis` folder. (Not all of therese are a strict requirement, however it was only tested with this configuration)
This `thesis` folder should have the following file structure:

<!-- https://tree.nathanfriend.com/?s=(%27options!(%27fancy!true~fullPathF~trailingSlashF~rootDotF)~I(%27I%27thesiENths_wENmeasurementE06A-1C06AL08BG36B-1CO6BLNfigureRQ4OH08B5HNplot-KRmergeJQ40H%27)~version!%271%27)*79907933-%20493K*93HOML5G3rebuildJ6data-folder-7%5Cn%208setup-9%20%20C%2FHEs%2FF!falseG%2F*H...Isource!J.bashOKconfigL-2CM8AN73O*3QM-1GRE0M5%01RQONMLKJIHGFEC98765430* -->
```
thesis/
├── ths_ws/ (ROS workspace can have anyname)
├── correction-data/... (Folder containing the frequency offset correction data)
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

## Plot-configs
**1a.** To generate plot configs for frequency response setups run (from `thesis/` folder):
```bash
ros2 run thesis_data_processing bodeplotter $PWD/measurements/<DATA_FOLDER_FOR_CONFIGURATION> --phase-method continuous -w all -F --save-plots $PWD/plot-configs/<SETUP>/ --save-plot-settings --save-only-plot-settings <OPTIONAL-ARGS>
```

**1b.** To generate plot configs for step response setups run (from `thesis/` folder ):
```bash
ros2 run thesis_data_processing step_response $PWD/measurements/<DATA_FOLDER_FOR_CONFIGURATION> -U --save-plots $PWD/plot-configs/<SETUP>/ --save-plot-settings --save-only-plot-settings <OPTIONAL-ARGS>
```

**2.** After which, the configs can be combined by running (from the `thesis/` folder):
```bash
ros2 run thesis_data_processing plot_config_merger --input ./plot-configs/<SETUP>/*/plot-config.pkl --output ./plot-configs/<SETUP>/merged-plot-config.pkl
```

## Figures
> Before generating figures it is recommended to first generate the appropriate plot-configs.

**1a.** To generate frequency response figures run the following command (from the `thesis/` folder):

> [!note]
> Correction data is **only recommend** for the **offset frequency trials**.
> This data is used to adjust for the gain at a frequency of 0 Hz.
> It can be generated from a *step response measurement* generated with `wheel_response_recorder/launch/step_zero_frequency_correction.launch.xml`.
>
> To generate the correction data run the following command:
> ```bash
> ros2 run thesis_data_processing $PWD/measurements/<CORRECTION_DATA_FOR_CONFIGURATION> --save-output $PWD/correction-data/
> # The correction file will match the source data foldername.
> ```

```bash
ros2 run thesis_data_processing bodeplotter $PWD/measurements/<DATA_FOLDER_FOR_CONFIGURATION> --phase-method continuous -w all -F --save-plots $PWD/figures/<SETUP>/ -ocm data -cdf $PWD/correction-data/<MATCHING-CORRECTIONDATA> --load-plot-settings $PWD/plot-configs/<CONFIG>/merged-plot-config.pkl <OPTIONAL-ARGS>
```


**1b.** To generate step response figures run the following command (from the `thesis/` folder):
```bash
ros2 run thesis_data_processing step_response $PWD/measurements/experimental/<DATA_FOLDER_FOR_CONFIGURATION> -U --save-plots $PWD/figures/<SETUP>/ --load-plot-settings $PWD/plot-configs/<SETUP>/merged-plot-config.pkl <OPTIONAL-ARGS>
```
