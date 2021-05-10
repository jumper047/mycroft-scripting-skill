# Copyright 2020, jumper047.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import yaml
import shutil
import random
from collections import namedtuple, Iterable

from mycroft import MycroftSkill, intent_handler
from mycroft.messagebus.message import Message
from mycroft.util.log import LOG


sleep_re = r"sleep\((?P<sleep_time>[0-9.]+)\)"
one_of_re = r"one_of\((?P<choices>.+)\)"

entity_re = r"\{(?P<entity>[a-zA-Z0-9_]+)\}"

FUNC_SEPARATOR = "|"
LOCAL_CONF = "scripts.yaml"
INTENTDIR_PREFIX = "tmp"
SEPARATOR = ";"


ScriptEntity = namedtuple("ScriptEntity", ["triggers", "commands", "from_yaml"])


class ScriptingSkill(MycroftSkill):

    def __init__(self):
        super().__init__("ScriptingSkill")
        self.scripts = dict()

    def initialize(self):
        # check if tmp folder exists
        try:
            os.mkdir(os.path.join(self.file_system.path, INTENTDIR_PREFIX))
        except FileExistsError:
            pass
        self.load_scripts()

        self.add_event('recognizer_loop:wakeword', self.handle_wakeword)


    def load_scripts(self):
        for name in self.scripts:
            self.remove_script(name)

        for name, (triggers, commands) in self.scripts_from_yaml().items():
            if name in self.scripts:
                self.remove_script(name)
            self.add_script(name, triggers, commands, True)


    def scripts_from_yaml(self):
        """Load dict with intents from yaml"""

        if self.file_system.exists(LOCAL_CONF):
            aliases = self.file_system.open(LOCAL_CONF, "r").read()
            return yaml.safe_load(aliases)
        else:
            return {}

    def add_script(self, name, triggers_str, commands_str, from_yaml=False):
        if name in self.scripts:
            raise KeyError("Alias \"%s\" already defined", name)
        triggers = triggers_str.split(SEPARATOR)
        commands = commands_str.split(SEPARATOR)
        entities = re.findall(entity_re, triggers_str)
        self.scripts[name] = ScriptEntity(triggers, commands, from_yaml)
        with self.file_system.open(os.path.join(
            self.file_system.path, 
            INTENTDIR_PREFIX,
            name + ".intent"), "w") as f:
            f.write("\n".join(triggers))
        intent_name = '{}:{}'.format(self.skill_id, name + ".intent")
        intent_file = os.path.join(self.file_system.path,
                                   INTENTDIR_PREFIX,
                                   name + ".intent")
        # register_padatious_intent
        self.intent_service.register_padatious_intent(intent_name, intent_file)
        self.add_event(intent_name, self.create_handler(commands, entities), 'mycroft.skill.handler')
        LOG.info("New alias registered: {}".format(name))

    def update_scripts_from_yaml(self):
        new_from_yaml = self.scripts_from_yaml()
        old_from_yaml = {name: self.scripts[name] for name in self.scripts
                         if self.scripts[name].from_yaml}
        # check names to delete
        for name in old_from_yaml:
            if name not in new_from_yaml:
                self.remove_script(name)
        # check names to add
        for name in new_from_yaml:
            if name not in old_from_yaml:
                self.add_script(name,
                                new_from_yaml[name].triggers,
                                new_from_yaml[name].commands)
        # check scripts to update
        for name in new_from_yaml:
            if name in old_from_yaml and old_from_yaml[name] != new_from_yaml[name]:
                self.remove_script(name)
                self.add_script(name,
                                new_from_yaml[name].triggers,
                                new_from_yaml[name].commands)

    def create_handler(self, commands, entities):

        def handler(message):
            com = list(commands)
            msg_data = {ent: message.data.get(ent, "") for ent in entities}

            def commands_runner(m=None):
                try:
                    next_msg = com.pop(0)
                except IndexError:
                    self.remove_event('recognizer_loop:audio_output_end')
                else:
                    next_msg = next_msg.strip().format(**msg_data)
                    sleep_match = re.search(sleep_re, next_msg)
                    one_of_match = re.search(one_of_re, next_msg)
                    if sleep_match:
                        time = float(sleep_match.group('sleep_time'))
                        LOG.info("Sleeping for %s seconds", time)
                        self.schedule_event(commands_runner, time)
                    elif one_of_match:
                        choices = one_of_match.group('choices').split(FUNC_SEPARATOR)
                        msg = random.choice(choices)
                        self.bus.emit(Message("recognizer_loop:utterance", {
                            'utterances': [msg],
                            'lang': self.lang}))
                    else:
                        self.bus.emit(Message("recognizer_loop:utterance", {
                            'utterances': [next_msg],
                            'lang': self.lang}))

            self.bus.emit(Message("recognizer_loop:utterance", {
                'utterances': [com.pop(0)],
                'lang': self.lang

            }))
            if len(com) > 0:
                self.add_event('recognizer_loop:audio_output_end', commands_runner)
            
        return handler

    def handle_wakeword(self):
        """Interrupt sequence on new wakeword"""
        self.remove_event('recognizer_loop:audio_output_end')
        
    def shutdown(self):
        self.remove_event('recognizer_loop:audio_output_end')
        shutil.rmtree(os.path.join(self.file_system.path, INTENTDIR_PREFIX))

def create_skill():
    return ScriptingSkill()
