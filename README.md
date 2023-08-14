# Batch Video Encoding

## Introduction

This is a wrapper for Lisa Melton's [Video Transcoding](https://github.com/lisamelton/video_transcoding) project.

Setting up and using Lisa's tools is beyond the scope of this README, but the basic goal is to convert rips from Blu-Ray or DVD to a more portable format that can be easily used in Plex or on mobile devices.

The goals of this project are:

1. Minimize hands-on time
2. Minimize option & configuration fatigue: the best options should be default, and things to tweak should be minimal

This project lets you provide a list of Matroska files to convert, along with global, and/or per-file settings. Then let it transcode an entire eason of Game of Thrones while you sleep.

**Video Transcoding**'s `transcode-video` does most of the heavy lifting. This tool just calls that command for each input file that needs converting.

Here are some features:

- Batch up a long list of transcode jobs and go to bed
- Any jobs that fail are noted and can be reattempted later when the problem is corrected
- Write an encoding report out to a file when finished
- Email an encoding report if an email address is provided
- Reduce interlacing effects if necessary
- Archive input files, logs, & configuration to a provided destination
- Most command line arguments can be saved to user config to be used as default

## Installation

Follow the installation instructions for **Video Transcoding** linked above.

If you can use `transcode-video` to convert a `.mkv` file to a h.264-encoded `.m4v`, you should be good to go. To test, try:

```Console
$ transcode-video --m4v /path/to/ripped.mkv /path/to/encoded.m4v
```
Optionally provide `--crop detect` and `--subtitle scan`, since this project uses those options.

Then install this project, as follows:

- Have an environment with Python 3.7 or later; a virtualenv is recommended
- Clone the project
- Install with pip:
  - `pip3 install [--user] /path/to/video-encoding`

## Basic Usage

To use `batchencode`, an encoding configuration is required that defines the batch of encoding jobs. You can automatically generate the config, edit it, then run the batch. To do so, run `batchencode` in two phases:

1. Run `batchencode` to generate an encoding configuration
2. After checking & editing the configuraiton, run `batchencode` to perform the list of encoding jobs in the configuration

Take the following as example:

- You have a directory `/home/user/encoding`
- Your encoding directory contains `file_01.mkv`, `file_02.mkv`, and `file_03.mkv`
- You want them encoded to `/home/user/videos/TV Shows/My TV Show/Season 01/My TV Show - s01e01.m4v`, etc.

You would generate the encoding config like so:

```Console
$ batchencode /home/user/encoding/encoding-jobs.json --video-list 'file*mkv' --outdir '/home/user/videos/TV Shows/My TV Show/Season 01/' --workdir '/home/user/encoding'
```

The `--video-list` CLI option may be either a shell glob, such as `'file*mkv'` or the path & name of a text file consisting of a line-by-line list of `.mkv` files. It is assumed all input files to be transcoded are in the directory specified by `--workdir`.

Manually review and edit the file, filling in each `output_title` field with `My TV Show s01e01`, etc.

Then run `batchencode` again. Assuming all the options in the encoding config are correct, no command line arguments are needed other than the config file itself:

```Console
$ batchencode /home/user/encoding/encoding-jobs.json
```

## Advanced Usage

`batchencode` provides several of options that can be specified as command line arguments or provided in the configuration file. Most of the command line options, if provided, will be added to the generated configuration file in phase 1.

The encoding options can be set and overridden with the following order of precedence:

1. Command line options specified during phase 2
2. Where it makes sense, options specified in individual job dictionaries in the configuration file
3. Global options specified in the configuration file
4. Defaults in ~/.config/batchencoder/batchencoder.json

Here's the help output from `batchencode`

```
usage: batchencode [-h] [--video-list VIDEO_LIST] [--outdir OUTDIR]
                   [--workdir WORKDIR] [--media-root MEDIA_ROOT]
                   [--archive-root ARCHIVE_ROOT] [--decomb] [--no-sleep]
                   [--disable-auto-burn]
                   [--burn-subtitle-num BURN_SUBTITLE_NUM]
                   [--add-subtitle ADD_SUBTITLE] [--report-path REPORT_PATH]
                   [--report-email REPORT_EMAIL] [--crop-params CROP_PARAMS]
                   [--movie] [--quality QUALITY] [--m4v] [--skip-encode]
                   [--write-user-defaults] [--chapters CHAPTERS]
                   config_file

positional arguments:
  config_file           name of encoding config file to load or create

optional arguments:
  -h, --help            show this help message and exit
  --video-list VIDEO_LIST
                        Text file containing a line-by-line list or file glob
                        to match a list of input files
  --outdir OUTDIR       Output directory where encoded videos should be
                        written
  --workdir WORKDIR     directory containing video files to encode
  --media-root MEDIA_ROOT
                        Root path to encoded files. Used to calculate
                        directory structure in the archive root.
  --archive-root ARCHIVE_ROOT
                        Root path to archive input files to. Directory
                        structure will be mirrored from media root.
  --decomb              optionally have Handbrake decomb video
  --no-sleep            prevent macOS from sleeping while encoding
  --disable-auto-burn   don't automatically burn first forced subtitle
  --burn-subtitle-num BURN_SUBTITLE_NUM
                        burn track selected by number into video
  --add-subtitle ADD_SUBTITLE
                        add track selected with language code (e.g., 'eng')
  --report-path REPORT_PATH
                        write encoding report to the specified path
  --report-email REPORT_EMAIL
                        email report to the specified email address
  --crop-params CROP_PARAMS
                        Crop parameters
  --movie               Treat this as Movie job rather than a TV show or other
                        category
  --quality QUALITY     Quality string to add to the output filename. E.g.,
                        '1080p' or '4K'. Only affects resulting filename
  --m4v                 Output MP4, (with '.m4v' extension) instead of
                        Matroska '.mkv' format
  --skip-encode         Skip encoding. If archive parameters are provided,
                        archiving will still happen.
  --write-user-defaults
                        Write default config to
                        ~/.config/batchencoder/batchencoder.json
  --chapters CHAPTERS   select chapters, single or range (default: all)
```

Let's go through the options. Later we'll cover how these can be specified in your configuration file rather than CLI options.

* `decomb`: Some input sources are interlaced, and "decombing" tells handbrake to do an intelligent form of deinterlacing. This is essential for sources such as DVD rips to eliminate unwatchable screen tearing.
* `no-sleep`: On macOS only, this tells the operating system to not sleep while `batchencode` is running.
* `disable-auto-burn`: Usually you want forced subtitles to be included, but on some input sources the results can be unexpected. In these situations, disable auto burning of forced subtitles
* `burn-subtitle-num` If the desired subtitle track isn't detected properly, or the wrong one is detected, you can specify which one to burn
* `report-path` Optionaly write a summary of the encoding jobs to the specified path
* `report-email` Optionally email a summary of the encoding jobs to the specified email address


### Archiving

If you want to archive your source material, provide `--media-root` and `--archive-root`. This allows `batchencode` to create a directory structure in your archive that mirrors your media. Say you want to archive to `/mnt/media archive/`, you would provide:

```
--archive-root "/mnt/media archive" --media-root "/home/user/videos"
```

This would create an archive directory structure that looked like:

```
/mnt/media archive
└── TV Shows
    └── My TV Show
        └── Season 01
            ├── My TV Show - s01e01.m4v
            │   └── file_01.mkv
            ├── My TV Show - s01e02.m4v
            │   └── file_02.mkv
            └── My TV Show - s01e03.m4v
                └── file_03.mkv
```

Each input file is archived in a directory structure that mirrors the encoded destination.
