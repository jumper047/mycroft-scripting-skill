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
import enum
from collections import namedtuple, Iterable

from mycroft import MycroftSkill, intent_handler
from mycroft.messagebus.message import Message
from mycroft.util.log import LOG


sleep_re = r"sleep\((?P<sleep_time>[0-9.]+)\)"
one_of_re = r"one_of\((?P<choices>.+)\)"

entity_re = r"\{(?P<entity>[a-zA-Z0-9_]+)\}"

TRIGGERS_SEPARATOR = ";"
FUNC_SEPARATOR = "|"
LOCAL_CONF = "scripts.yaml"
INTENTDIR_PREFIX = "tmp"
SEP_START = "&"
SEP_END = ("&", "!")  # go to next and wait speech separators


DEFAULT_CONFIG = """
Example script:                               # script name
- run example script; execute example script  # trigger phrases
- say example &! script executed              # actions
"""


ScriptEntity = namedtuple("ScriptEntity", ["triggers", "commands", "from_yaml"])
Action = namedtuple("Action", ["command", "data", "wait_reply"])


class Command(enum.Enum):
    RAW = 0
    ONE_OF = 1
    SLEEP = 2


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

        if not self.file_system.exists(LOCAL_CONF):
            self.write_example_config()
        
        self.load_scripts()

        self.add_event('recognizer_loop:wakeword', self.handle_wakeword)


    def load_scripts(self):
        for name in self.scripts:
            self.remove_script(name)

        try:
            scripts = self.scripts_from_yaml()
        except yaml.YAMLError:
            self.speak_dialog('scripts.load.failed.dialog')
            return None

        for name, (triggers, commands, from_yaml) in scripts.items():
            if name in self.scripts:
                self.remove_script(name)
            self.add_script(name, triggers, commands, True)


    def scripts_from_yaml(self):
        """Load dict with intents from yaml"""

        if self.file_system.exists(LOCAL_CONF):
            with self.file_system.open(LOCAL_CONF, "r") as f:
                scripts = yaml.load(f.read())
            return {x: ScriptEntity(*y, True) for x, y in scripts.items()}
        else:
            return {}


    def write_example_config(self):
        with self.file_system.open(LOCAL_CONF, 'w') as f:
            f.write(DEFAULT_CONFIG)
        

    def add_script(self, name, triggers_str, commands_str, from_yaml=False):
        if name in self.scripts:
            raise KeyError("Alias \"%s\" already defined", name)
        triggers = triggers_str.split(TRIGGERS_SEPARATOR)
        actions = self.parse_command(commands_str)
        entities = re.findall(entity_re, triggers_str)
        self.scripts[name] = ScriptEntity(triggers, actions, from_yaml)
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
        self.add_event(intent_name, self.create_handler(actions, entities), 'mycroft.skill.handler')
        LOG.info("New alias registered: {}".format(name))


    def remove_script(self, name):
        # if self.scripts[name].from_yaml:
            # raise ValueError("Alias named \"%s\" defined in yaml so it can't be deleted", name)
        del(self.scripts[name])
        self.disable_intent(name + ".intent")
        self.remove_event('{}:{}'.format(self.skill_id, name + ".intent"))


    def update_from_yaml(self):
        """Update scripts from yaml config"""

        new_from_yaml = self.scripts_from_yaml()
        old_from_yaml = {name: self.scripts[name] for name in self.scripts
                         if self.scripts[name].from_yaml}
        LOG.info("new:  %s", new_from_yaml)
        LOG.info("old: %s", old_from_yaml)
        LOG.info("scripts: %s", self.scripts)
        # check names to delete
        for name in old_from_yaml:
            if name not in new_from_yaml:
                self.remove_script(name)
        # check names to add
        for name in new_from_yaml:
            if name not in old_from_yaml:
                self.add_script(name,
                                new_from_yaml[name].triggers,
                                new_from_yaml[name].commands,
                                True)
        # check scripts to update
        for name in new_from_yaml:
            if name in old_from_yaml and old_from_yaml[name] != new_from_yaml[name]:
                self.remove_script(name)
                self.add_script(name,
                                new_from_yaml[name].triggers,
                                new_from_yaml[name].commands,
                                True)


    def update_from_yaml_and_report(self):
        """Update script from yaml and say if something went wrong.

        Return True on successfull update False othervise"""

        try:
            self.update_from_yaml()
        except yaml.YAMLError:
            self.speak_dialog('scripts.update.failed.dialog')
            return False
        else:
            return True


    def parse_command(self, comm_string):
        actions = []
        curr_chunk = ""
        
        def get_command_data(chunk):
            sleep_match = re.search(sleep_re, curr_chunk)
            one_of_match = re.search(one_of_re, curr_chunk)
            if sleep_match:
                command = Command.SLEEP
                data = float(sleep_match.group('sleep_time'))
            elif one_of_match:
                command = Command.ONE_OF
                data = [x.strip() for x in one_of_match.group('choices').split(FUNC_SEPARATOR)]
            else:
                command = Command.RAW
                data = curr_chunk.strip()
            LOG.info("get command data from %s result %s %s", chunk, command, data)
            return command, data

        for symbol in comm_string:
            if len(curr_chunk) > 0 and symbol in SEP_END and curr_chunk[-1] == SEP_START:
                if symbol == SEP_END[0]:
                    wait_reply = False
                else:
                    wait_reply = True
                curr_chunk = curr_chunk[:-1]  # strip first separator
                command, data = get_command_data(curr_chunk)
                actions.append(Action(command, data, wait_reply))
                curr_chunk = ""
            else:
                curr_chunk += symbol
        else:
            command, data = get_command_data(curr_chunk)
            actions.append(Action(command, data, False))
        for a in actions:
            LOG.info("Actions: %s", a)
        return actions
                    

    def create_handler(self, commands, entities):

        def handler(message):
            com = list(commands)
            msg_data = {ent: message.data.get(ent, "") for ent in entities}

            def commands_runner(m=None):
                # TODO: randomize handler to distinguish different tasks
                LOG.info("Runner started for command %s", com)
                try:
                    action = com.pop(0)
                except IndexError:
                    return None
                else:
                    if action.command == Command.SLEEP:
                        self.schedule_event(commands_runner, action.data)
                        return None
                    elif action.command == Command.ONE_OF:
                        msg = random.choice(action.data)
                    elif action.command == Command.RAW:# raw
                        msg = action.data
                    LOG.info("Action is %s", action)
                    LOG.info("Message is %s", msg)
                    msg.format(**msg_data)
                    self.bus.emit(Message("recognizer_loop:utterance", {
                        'utterances': [msg],
                        'lang': self.lang
                    }))
                    if action.wait_reply:
                        self.add_event('recognizer_loop:audio_output_end', commands_runner, once=True)
                    else:
                        self.schedule_event(commands_runner, 0.5)

            commands_runner()
            
        return handler


    def handle_wakeword(self):
        """Interrupt sequence on new wakeword"""
        self.remove_event('recognizer_loop:audio_output_end')


    @intent_handler('reload.config.intent')
    def handle_reload_config_request(self):
        before_update = {name: self.scripts[name] for name in self.scripts
                         if self.scripts[name].from_yaml}
        if not self.update_from_yaml():
            return None
        after_update = {name: self.scripts[name] for name in self.scripts
                         if self.scripts[name].from_yaml}
        if before_update == after_update:
            self.speak_dialog('no.scripts.updated.dialog')
        else:
            self.speak_dialog('scripts.updated.dialog')
        
        
    def shutdown(self):
        self.remove_event('recognizer_loop:audio_output_end')
        shutil.rmtree(os.path.join(self.file_system.path, INTENTDIR_PREFIX))


def create_skill():
    return ScriptingSkill()
