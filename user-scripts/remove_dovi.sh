#!/bin/sh -e

_input_file="$1"


_base_layer_out="bl.hevc"
_input_ext=".mkv"
_input_basename="$(basename -s $_input_ext "$_input_file")"

_output_file="$_input_basename"-no-dovi"$_input_ext"

ffmpeg -i "$_input_file" -c:v copy -bsf:v hevc_mp4toannexb -f hevc - | dovi_tool remove - -o "$_base_layer_out"


mkvmerge --output "$_output_file" "$_base_layer_out" --no-video "$_input_file"

rm "$_base_layer_out"
