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
import yaml
from collections import namedtuple, Iterable

from mycroft import MycroftSkill, intent_handler
from mycroft.messagebus.message import Message
from mycroft.util.log import LOG


LOCAL_CONF = "aliases.yaml"
INTENTDIR_PREFIX = "tmp"
COMMANDS_SEPARATOR = ";"

AliasEntity = namedtuple("AliasEntity", ["alias", "command", "from_yaml"])


class AliasSkill(MycroftSkill):
    def __init__(self):
        super().__init__("AliasSkill")
        self.aliases = dict()

    def initialize(self):
        # check if tmp folder exists
        try:
            os.mkdir(os.path.join(self.file_system.path, INTENTDIR_PREFIX))
        except FileExistsError:
            pass
        self.load_aliases()

        self.add_event('recognizer_loop:wakeword', self.handle_wakeword)

    def load_aliases(self):
        for name in self.aliases:
            self.remove_alias(name)

        LOG.info(self.settings.get("aliases", {}))


        for name, (alias, command) in self.settings.get("aliases", {}):
            self.add_alias(name, alias, command, False)

        for name, (alias, command) in self.aliases_from_yaml().items():
            if name in self.aliases:
                self.remove_alias(name)
            self.add_alias(name, alias, command, True)

        LOG.info("Aliases loaded.")

    def save_aliases(self):
        aliases = dict()
        for name, entity in self.aliases.items():
            if not entity.from_yaml:
                aliases[name] = (entity.alias, entity.command)
        self.settings["aliases"] = aliases

    def aliases_from_yaml(self):
        """Load dict with intents from yaml"""

        if self.file_system.exists(LOCAL_CONF):
            aliases = self.file_system.open(LOCAL_CONF, "r").read()
            return yaml.safe_load(aliases)
        else:
            return {}

        
    def remove_alias(self, name):
        if self.aliases[name].from_yaml:
            raise ValueError("Alias named \"%s\" defined in yaml so it can't be deleted", name)
        del(self.aliases[name])
        self.disable_intent(name + ".intent")
        self.remove_event('{}:{}'.format(self.skill_id, name + ".intent"))


    def add_alias(self, name, alias, command, from_yaml=False):
        if name in self.aliases:
            raise KeyError("Alias \"%s\" already defined", name)
        self.aliases[name] = AliasEntity(alias, command, from_yaml)
        with self.file_system.open(os.path.join(
            self.file_system.path, 
            INTENTDIR_PREFIX,
            name + ".intent"), "w") as f:
            f.write(alias)
        intent_name = '{}:{}'.format(self.skill_id, name + ".intent")
        intent_file = os.path.join(self.file_system.path,
                                   INTENTDIR_PREFIX,
                                   name + ".intent")
        # register_padatious_intent
        self.intent_service.register_padatious_intent(intent_name, intent_file)
        self.add_event(intent_name, self.create_handler(command), 'mycroft.skill.handler')
        LOG.info("Registered new alias: {}".format(name))


    def create_handler(self, command):

        if COMMANDS_SEPARATOR in command:
            commands = command.split(COMMANDS_SEPARATOR)
            def handler(message):
                com = list(commands)
                def commands_runner(m=None):
                    try:
                        next_msg = com.pop(0)
                    except IndexError:
                        self.remove_event('recognizer_loop:audio_output_end')
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
        else:
            def handler(message):
                self.bus.emit(Message("recognizer_loop:utterance", {
                    'utterances': [command],
                    'lang': self.lang
                }))                
            
        return handler

    def handle_wakeword(self):
        """Interrupt sequence on new wakeword"""
        self.remove_event('recognizer_loop:audio_output_end')

    @intent_handler("list.aliases.intent")
    def list_aliases_handler(self, message):
        names = ",".join(self.aliases)
        self.speak_dialog('list.aliases', {'aliases': names})

    @intent_handler("expose.aliases.intent")
    def expose_shortcut_handler(self, message):
        name = message.data.get('alias')
        # TODO: i think it should be something like fuzzy matching
        if name in self.aliases:
            self.speak_dialog('expose.aliases',
                              {'aliases': name,
                               'phrases': self.aliases[name].alias,
                               'commands': self.aliases[name].command})
        else:
            self.speak_dialog('alias.not.found', {'alias': names})

    @intent_handler("delete.aliases.intent")
    def delete_shortcut_handler(self, message):
        shortcut = message.data.get('alias')
        if shortcut in self.aliases:
            del(self.aliases[shortcut])
            self.disable_intent(shortcut + ".intent")
            self.remove_event('{}:{}'.format(self.skill_id,
                                             shortcut + ".intent"))
            dialog = 'delete.alias'
        else:
            dialog = 'alias.not.found'
        self.speak_dialog(dialog, {'alias': shortcut})

    @intent_handler("create.alias.intent")
    def create_shortcut_handler(self, message):


        name = self.get_response('input.alias.name',
                                 validator=lambda utt: utt not in self.aliases, 
                                 on_fail='name.already.used',
                                 num_retries=1)
        if name is None:
            return None

        alias = self.get_response('input.alias')
        command = self.get_response('input.command')
        self.add_alias(name, alias, command)
        self.save_aliases()
        
    def shutdown(self):
        self.save_aliases()

def create_skill():
    return AliasSkill()
