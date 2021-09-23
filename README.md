# Batch Video Encoding

## Introduction

This is a wrapper for Don Melton's [Video Transcoding](https://github.com/donmelton/video_transcoding) project.

Setting up and using Don's tools is beyond the scope of this README, but the basic goal is to convert rips from Blu-Ray or DVD to a more portable format that can be easily used in Plex or on mobile devices.

The goals of this project are:

1. Minimize hands-on time
2. Minimize option & configuration fatigue: the best options should be default, and things to tweak should be minimal

This project lets you provide a list of Matroska files to convert, along with global, and/or per-file settings. Then let it transcode an entire eason of Game of Thrones while you sleep.

**Video Transcoding**'s `transcode-video` does most of the heavy lifting. This tool just calls that command for each input file that needs converting

Here are some features:

- Batch up a long list of transcode jobs and walk away
- Any jobs that fail are noted and can be reattempted later when the problem is corrected
- Write an encoding report out to a file when finished
- Email an enocding report if an exmail address is provided
- Reduce interlacing effects if necessary
- Archive input files to a provided destination
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

For example, say you have a directory `/home/user/encoding` containing `file_01.mkv`, `file_02.mkv`, and `file_03.mkv`, and you want them encoded to `/home/user/videos/TV Shows/My TV Show/Season 01/My TV Show - s01e01.m4v`, etc. You would generate the encoding config like so:

```Console
$ batchencode /home/user/encoding/encoding-jobs.json --video-list 'file*mkv' --outdir '/home/user/videos/TV Shows/My TV Show/' --workdir '/home/user/encoding'
```

The `--video-list` CLI option may be either a shell glob, such as `'file*mkv'` or the path & name of a text file consisting of a line-by-line list of `.mkv` files. It is assumed all input files to be transcoded are in the directory specified by `--workdir`.

Manually review and edit the file, filling in each `output_title` field with `My TV Show s01e01`, etc.

Then run `batchencode` again. Assuming all the options in the encoding config are correct, no command line arguments are needed other than the config file itself:

```Console
$ batchencode /home/user/encoding/encoding-jobs.json
```

## Advanced Usage

`batchencode` provides several of options that can be specified as command line arguments or provided in the configuration file. Most of the command line options, if provided, will be added to the generated configuration file in phase 1. In phase 2, those same command line options can be used to override any options in the configuration file.

More to come about advanced usage.
