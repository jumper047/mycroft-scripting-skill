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

from mycroft import MycroftSkill, intent_handler
from mycroft.messagebus.message import Message
from mycroft.util.log import LOG


class ScriptingSkill(MycroftSkill):
    def __init__(self):
        super().__init__("ScriptingSkill")

    def initialize(self):

        self.load_shortcuts()

        LOG.info("Registering shortcuts from settings: {}".format(list(self.shortcuts.keys())))
        for k, v in self.shortcuts.items():
            self.register_shortcut_intent(k, **v)
        LOG.info("Done with registering from settings")

        self.add_event('recognizer_loop:wakeword', self.handle_wakeword)

        self.settings_change_callback = self.on_settings_changed
        self.on_settings_changed()

    def load_shortcuts(self):
        shortcuts = self.settings.get("shortcuts", dict())
        self.shortcuts = dict()
        for s in shortcuts:
            try:
                phrases = shortcuts[s]["phrases"].split(";")
                commands = shortcuts[s]["commands"].split(";")
            except KeyError as e:
                LOG.warning("Error while loading shortcut {}: {}".format(s, e))
            else:
                self.shortcuts[s] = dict(phrases=phrases, commands=commands)

    def save_shortcuts(self):
        shc = dict()
        for s in self.shortcuts:
            shc[s] = dict(phrases=";".join(self.shortcuts[s]["phrases"]),
                          commands=";".join(self.shortcuts[s]["commands"]))
        self.settings["shortcuts"] = shc
        self.settings["shortcuts_names"] = ";".join(self.shortcuts.keys())

    def register_shortcut_intent(self, name, phrases, commands):
        with self.file_system.open(name + ".intent", "w") as f:
            f.write("\n".join(phrases))
        intent_name = '{}:{}'.format(self.skill_id, name + ".intent")
        intent_file = os.path.join(self.file_system.path, name + ".intent")
        # register_padatious_intent
        self.intent_service.register_padatious_intent(intent_name, intent_file)
        self.add_event(intent_name, self.create_handler(commands), 'mycroft.skill.handler')
        LOG.info("Registered new shortcut: {}".format(name))

    def refresh_shortcut_entity(self):
        with self.file_system.open("shortcut.entity", "w") as f:
            f.write("\n".join(self.shortcuts.keys()))
        entity_name = '{}:{}'.format(self.skill_id, "shortcut.entity")
        entity_file = os.path.join(self.file_system.path, "shortcut.entity")
        self.intent_service.register_padatious_entity(entity_name, entity_file)

    def create_handler(self, commands):
        commands = tuple(commands)
        def handler(message):
            com = list(commands)
            def commands_runner(m=None):
                try:
                    next_msg = com.pop(0)
                except IndexError:
                    self.remove_event('recognizer_loop:audio_output_start')
                else:
                    self.bus.emit(Message("recognizer_loop:utterance", {
                        'utterances': [next_msg],
                        'lang': self.lang}))

            self.bus.emit(Message("recognizer_loop:utterance", {
                'utterances': [com.pop(0)],
                'lang': self.lang
            }))
            if len(com) > 0:
                self.add_event('recognizer_loop:audio_output_start', commands_runner)
            
        return handler


    def on_settings_changed(self):
        name = self.settings.get("new_shortcut", "")
        phrases = self.settings.get("new_phrases", "").split(";")
        commands = self.settings.get("new_commands", "").split(";")

        for i in ["new_shortcut", "new_phrases", "new_commands"]:
            self.settings[i] = ""
        
        if "" not in (name, phrases, commands):
            self.shortcuts[name] = dict(phrases=phrases, commands=commands)
            self.disable_intent(name + ".intent")
            self.remove_event('{}:{}'.format(self.skill_id, name + ".intent"))
            self.register_shortcut_intent(name, phrases, commands)
        self.refresh_shortcut_entity()
        self.save_shortcuts()

    def handle_wakeword(self):
        """remove event in case something went wrong"""
        self.remove_event('recognizer_loop:audio_output_start')

    @intent_handler("list.shortcuts.intent")
    def list_shortcuts_handler(self, message):
        shcuts = ",".join(self.shortcuts)
        self.speak_dialog('list.shortcuts', {'shortcuts': shcuts})

    @intent_handler("expose.shortcut.intent")
    def expose_shortcut_handler(self, message):
        shortcut = message.data.get('shortcut')
        if shortcut in self.shortcuts:
            self.speak_dialog('expose.shortcut',
                              {'shortcut': shortcut,
                               'phrases': ",".join(self.shortcuts[shortcut]["phrases"]),
                               'commands': ",".join(self.shortcuts[shortcut]["commands"])})
        else:
            self.speak_dialog('shortcut.not.found', {'shortcut': shortcut})

    @intent_handler("delete.shortcuts.intent")
    def delete_shortcut_handler(self, message):
        shortcut = message.data.get('shortcut')
        if shortcut in self.shortcuts:
            del(self.shortcuts[shortcut])
            self.disable_intent(shortcut + ".intent")
            self.remove_event('{}:{}'.format(self.skill_id,
                                             shortcut + ".intent"))
            dialog = 'delete.shortcut'
        else:
            dialog = 'shortcut.not.found'
        self.speak_dialog(dialog, {'shortcut': shortcut})

    @intent_handler("create.shortcut.intent")
    def create_shortcut_handler(self, message):
        pass

    # def stop(self):
    #     pass

    def shutdown(self):
        self.save_shortcuts()

def create_skill():
    return ScriptingSkill()
