# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import re
import os
import sys
import ast

from PySide import QtGui
from PySide import QtCore

from hiero.exporters import FnAudioExportTask
from hiero.exporters import FnAudioExportUI

import sgtk
from .base import ShotgunHieroObjectBase
from .collating_exporter import CollatingExporter, CollatedShotPreset

from hiero import core
from hiero.core import *


class ShotgunAudioExporterUI(ShotgunHieroObjectBase, FnAudioExportUI.AudioExportUI):
    """
    Custom Preferences UI for the shotgun audio exporter
    """
    def __init__(self, preset):
        FnAudioExportUI.AudioExportUI.__init__(self, preset)
        self._displayName = "Shotgun Audio Export"
        self._taskType = ShotgunAudioExporter

class ShotgunAudioExporter(ShotgunHieroObjectBase, FnAudioExportTask.AudioExportTask, CollatingExporter):
    """
    Create Audio object and send to Shotgun
    """
    def __init__(self, initDict):
        """
        Constructor
        """
        FnAudioExportTask.AudioExportTask.__init__(self, initDict)
        CollatingExporter.__init__(self)

        self._resolved_export_path = None
        self._sequence_name = None
        self._thumbnail = None

        # Only publish combined audio. This is done by only publishing video track output
        self._do_publish = self._item.mediaType() is core.TrackItem.MediaType.kVideo

    def sequenceName(self):
        """override default sequenceName() to handle collated shots"""
        try:
            if self.isCollated():
                return self._parentSequence.name()
            else:
                return FnAudioExportTask.AudioExportTask.sequenceName(self)
        except AttributeError:
            return FnAudioExportTask.AudioExportTask.sequenceName(self)

    def startTask(self):
        """ Run Task """
        if self._resolved_export_path is None:
            self._resolved_export_path = self.resolvedExportPath()
            self._tk_version = self._formatTkVersionString(self.versionString())
            self._sequence_name = self.sequenceName()

            # convert slashes to native os style..
            self._resolved_export_path = self._resolved_export_path.replace("/", os.path.sep)

        # call the get_shot hook
        ########################
        if self.app.shot_count == 0:
            self.app.preprocess_data = {}

        # associate publishes with correct shot, which will be the hero item
        # if we are collating
        if self.isCollated() and not self.isHero():
            item = self.heroItem()
        else:
            item = self._item

        # store the shot for use in finishTask
        self._sg_shot = self.app.execute_hook("hook_get_shot", task=self, item=item, data=self.app.preprocess_data)

        ##############################
        # see if we get a task to use
        self._sg_task = None
        try:
            task_filter = self.app.get_setting("default_task_filter", "[]")
            task_filter = ast.literal_eval(task_filter)
            task_filter.append(["entity", "is", self._sg_shot])
            tasks = self.app.shotgun.find("Task", task_filter)
            if len(tasks) == 1:
                self._sg_task = tasks[0]
        except ValueError:
            # continue without task
            setting = self.app.get_setting("default_task_filter", "[]")
            self.app.log_error("Invalid value for 'default_task_filter': %s" % setting)

        # figure out the thumbnail frame
        ##########################
        source = self._item.source()
        self._thumbnail = source.thumbnail(source.posterFrame())

        return FnAudioExportTask.AudioExportTask.startTask(self)

    # Temporarily overwritten from FnAudioExportTask to test things out...
    def taskStep(self):
      if self.isCollated() and not self.isHero():
        item = self.heroItem()
        print "Hero Item: ", id(item), ' -- ', id(self._item)
      else:
        item = self._item
  
      # Write out the audio bounce down
      if isinstance(item, (Sequence, TrackItem)):
        if self._sequenceHasAudio(self._sequence):
          self._audioFile = self.resolvedExportPath()
  
          filename, ext = os.path.splitext(self._audioFile)
          if ext.lower() != ".wav":
            self._audioFile = filename + ".wav"
  
          if isinstance(item, Sequence):
            start, end = self.sequenceInOutPoints(item, 0, item.duration() - 1)
  
            # If sequence, write out full length
            item.writeAudioToFile(self._audioFile, start, end)
  
          elif isinstance(item, TrackItem):
            handles = self._cutHandles if self._cutHandles is not None else 0
            start, end = (item.timelineIn() - handles), (item.timelineOut() + handles) + 1
            print "Audio Export Item Id: ", item.guid(), ' -- type: ', type(item).__name__
            print "Audio export range (track): [{start}, {end}] -- handles: {handles} -- {id} / {type}".format(start=start, end=end, handles=handles, id=id(self), type=type(self).__name__)
            print "Sequence id: ", self._sequence.guid()
            timein, timeout = self.collatedOutputRange()
            print "Timein: ", timein, " / ", timeout
            start = timein
            end = timeout
            # If trackitem write out just the audio within the cut
            self._sequence.writeAudioToFile(self._audioFile, start, end)
  
      elif isinstance(item, Clip):
        # If item is clip, we're writing out the clip audio not the whole sequence
        if item.mediaSource().hasAudio():
          self._audioFile = self.resolvedExportPath()
  
          if (os.path.splitext(self._audioFile)[1]).lower() != ".wav":
            self._audioFile += ".wav"
  
          # If sequence or clip, write out full length
          item.writeAudioToFile(self._audioFile)
  
  
      self._finished = True
  
      return False

    def taskStep222(self):
        '''
        # Write out the audio bounce down
        if isinstance(self._item, (Sequence, TrackItem)):
          if self._sequenceHasAudio(self._sequence):
            self._audioFile = self.resolvedExportPath()

            filename, ext = os.path.splitext(self._audioFile)
            if ext.lower() != ".wav":
              self._audioFile = filename + ".wav"

            if isinstance(self._item, Sequence):
              start, end = self.sequenceInOutPoints(self._item, 0, self._item.duration() - 1)
              print "Audio export range (sequence): [{start}, {end}] -- {id}".format(start=start, end=end, id=id(self))

              # If sequence, write out full length
              self._item.writeAudioToFile(self._audioFile, start, end)

            elif isinstance(self._item, TrackItem):
              handles = self._cutHandles if self._cutHandles is not None else 0
              start, end = (self._item.timelineIn() - handles), (self._item.timelineOut() + handles) + 1
              start = self._sequence.inTime()
              end = self._sequence.outTime()
              print "Audio export range (track): [{start}, {end}] -- handles: {handles} -- {id}".format(start=start, end=end, handles=handles, id=id(self))
              # If trackitem write out just the audio within the cut
              self._sequence.writeAudioToFile(self._audioFile, start, end)

        elif isinstance(self._item, Clip):
          # If item is clip, we're writing out the clip audio not the whole sequence
          if self._item.mediaSource().hasAudio():
            self._audioFile = self.resolvedExportPath()
            print "CLIP EXPORT!!!!!!!!!!!!!!!!!!!!!!!!!!!!"

            if (os.path.splitext(self._audioFile)[1]).lower() != ".wav":
              self._audioFile += ".wav"

            # If sequence or clip, write out full length
            self._item.writeAudioToFile(self._audioFile)


        self._finished = True

        return False
        '''
        '''
        if self.isCollated():
            self._audioFile = self.resolvedExportPath()

            filename, ext = os.path.splitext(self._audioFile)
            if ext.lower() != ".wav":
              self._audioFile = filename + ".wav"

            if isinstance(self._item, Sequence):
              start, end = self.sequenceInOutPoints(self._item, 0, self._item.duration() - 1)
              print "Audio export range (sequence): [{start}, {end}] -- {id}".format(start=start, end=end, id=id(self))

              # If sequence, write out full length
              self._item.writeAudioToFile(self._audioFile, start, end)

            elif isinstance(self._item, TrackItem):
              handles = self._cutHandles if self._cutHandles is not None else 0
              start, end = (self._item.timelineIn() - handles), (self._item.timelineOut() + handles) + 1
              #start = self._sequence.inTime()
              #end = self._sequence.outTime()
              print "Audio export range (track): [{start}, {end}] -- {id}".format(start=start, end=end, id=id(self))
              # If trackitem write out just the audio within the cut
              self._sequence.writeAudioToFile(self._audioFile, start, end)
        '''

        return FnAudioExportTask.AudioExportTask.taskStep(self)

    def finishTask(self):
        """ Finish Task """
        # run base class implementation
        FnAudioExportTask.AudioExportTask.finishTask(self)
        print "Finishing: ", id(self)

        if self._do_publish:
            self._publish()

    def _publish(self):
        """
        Publish task output.
        """
        ctx = self.app.tank.context_from_entity('Shot', self._sg_shot['id'])
        published_file_type = self.app.get_setting('audio_published_file_type', "Hiero Audio")

        args = {
            "tk": self.app.tank,
            "context": ctx,
            "path": self._resolved_export_path,
            "name": os.path.basename(self._resolved_export_path),
            "version_number": int(self._tk_version),
            "published_file_type": published_file_type,
        }

        if self._sg_task is not None:
            args["task"] = self._sg_task

        # register publish
        self.app.log_debug("Register publish in shotgun: %s" % str(args))
        pub_data = sgtk.util.register_publish(**args)

        # upload thumbnail for publish
        self._upload_thumbnail_to_sg(pub_data, self._thumbnail)

class ShotgunAudioPreset(ShotgunHieroObjectBase, FnAudioExportTask.AudioExportPreset, CollatedShotPreset):
    """
    Settings for the shotgun audio export step
    """
    def __init__(self, name, properties):
        FnAudioExportTask.AudioExportPreset.__init__(self, name, properties)
        self._parentType = ShotgunAudioExporter
        CollatedShotPreset.__init__(self, self.properties())
