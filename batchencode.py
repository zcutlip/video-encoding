#!/usr/bin/env python

import os
import subprocess
import sys
from shutil import copyfile
class BatchEncoder(object):
    QUEUE_FILE="queue.txt"
    def __init__(self, workdir,outdir,decomb=False):
        self.decomb=decomb
        self.workdir = workdir
        self.queue_file="%s/%s" % (self.workdir,self.QUEUE_FILE)
        self.outdir = outdir
        self._sanity_check_dirs()
        self._backup_queue_file()
        self._process_queue_file()

    def wait(self):
        print "Running all encoders."
        for encoder,line in self.encoders:
            encoder.run()
            encoder.wait()
            self._delete_line_from_queue(line)

    def _sanity_check_dirs(self):
        if not os.path.isdir(self.workdir):
            raise Exception("Working directory not found: %s" % self.workdir)

        if not os.path.isdir(self.outdir):
            raise Exception("Output directory not found: %s" % self.outdir)

        if not os.path.exists("%s" % self.queue_file):
            raise Exception("Can't find queue file: %s" % self.queue_file)


    def _process_queue_file(self):
        self.encoders=[]
        for line in open(self.queue_file).readlines():
            line=line.rstrip()
            (input_file,output_title)=line.split(',',1)
            encoder=SingleEncoder(self.workdir,self.outdir,input_file,output_title,decomb=self.decomb)
            self.encoders.append((encoder,line))

    def _backup_queue_file(self):
        queue_file_backup="%s.orig" % self.queue_file
        copyfile(self.queue_file,queue_file_backup)

    def _delete_line_from_queue(self,line):
        output=[]
        for queue_line in open(self.queue_file,"rb"):
            if line != queue_line.rstrip():
                output.append(queue_line)

        queue_out=open(self.queue_file,"wb")
        for outline in output:
            queue_out.write(outline)
        queue_out.close()


class SingleEncoder(object):
    TRANSCODE="transcode-video"
    def __init__(self, workdir,outdir,input_file,output_title,decomb=False):
        self.decomb=decomb
        self.outdir = outdir
        self.input_file=input_file
        self.input_file_basename=os.path.basename(self.input_file)
        #self.fq_input_file="%s/%s" % (workdir,input_file)
        self.crops_dir="%s/%s" %(workdir,"Crops")
        self.output_title = output_title
        self.outlog="%s.log" % self.input_file
        self.fq_output_file="%s/%s.m4v" % (self.outdir,self.output_title)
        self._sanity_check_dirs()
        self.command=self._build_command()

    def run(self):
        print "Running:"
        print self.command
        self.outlog_file=open(self.outlog,"wb",0)
        self.process=subprocess.Popen(self.command,stdout=self.outlog_file,stderr=self.outlog_file,bufsize=0)

    def wait(self):
        print "Waiting for encode job of %s to complete." % self.input_file
        self.process.wait()
        print "Done."

    def _sanity_check_dirs(self):
        if not os.path.exists(self.input_file):
            raise Exception("Input file not found: %s" % self.input_file)

        if not os.path.isdir(self.outdir):
            raise Exception("Output directory not found: %s" % self.outdir)

    def _build_command(self):
        crop_option=self._get_crop_option()
        subtitle_option=self._get_sub_option()
        decomb_option=self._get_decomb_option()
        command=[self.TRANSCODE]
        if crop_option:
            for opt in crop_option:
                command.append(opt)
        if subtitle_option:
            for opt in subtitle_option:
                command.append(opt)
        if decomb_option:
            for opt in decomb_option:
                command.append(opt)
        command.append("--m4v")
        command.append(self.input_file)
        command.append("--output")
        command.append(self.fq_output_file)
        return command

    def _get_sub_option(self):
        """
        Build option list for burning subtitles.
        Eventually this will be configurable at run-time and may return None.
        """
        sub_opt=["--burn-subtitle","scan"]

        return sub_opt

    def _get_crop_option(self):
        """build option list for cropping video."""
        crop_file="%s/%s_crop.txt" % (self.crops_dir,self.input_file_basename)

        try:
            crop_val=open(crop_file,"rb").readline().strip()
            crop_opt=["--crop",crop_val]
        except Exception as e:
            print e
            crop_opt=["--crop","detect"]

        return crop_opt
    def _get_decomb_option(self):
        """
        Do we need to set decombing?
        """
        decomb_option=None
        if self.decomb:
            decomb_option=["--filter","decomb"]
        return decomb_option


def main():
    decomb=False
    workdir=sys.argv[1]
    outdir=sys.argv[2]
    if len(sys.argv)>3 and sys.argv[3] == "decomb":
        decomb=True

    print "Creating batch encoder."
    encoder=BatchEncoder(workdir,outdir,decomb=decomb)
    print "Waiting for encoder to finish."
    encoder.wait()
    print "Batch encoder done."

if __name__ == '__main__':
    main()
