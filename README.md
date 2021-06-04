# <img src='https://raw.githack.com/FortAwesome/Font-Awesome/master/svgs/solid/code.svg' card_color='#22a7f0' width='50' height='50' style='vertical-align:bottom'/> Scripting skill

Create aliases and simple scripts

## About
This skill implements rudimental scripting language for mycroft.
Scripts consists of two parts: trigger and action. Trigger is, in fact, padatious intent and described with almost same syntax. Action activated when recognized speech triggered script. Scripts stored in yaml config file on mycroft locally in ~/.mycroft/skills/ScriptingSkill/scripts.yaml

### Triggers
Triggers syntax almost same as mycroft's padatious intents. You can read about them here:  https://mycroft-ai.gitbook.io/docs/skill-development/user-interaction/intents/padatious-intents
The only difference is phrases separator - instead of new line you should use semicolon, ";"
	Also it is possible to capture some input with `{placeholder}` syntax and use it later in actions.

### Actions
Commands in action string can be separated with two separator types: "&&" and "&!". First one means next command will be sent to mycroft immediately after previous, second one - next command will be executed next to answer to previous command. At this moment there are three types of commands:
* Plain command - simple text, it will be sent to mycroft messagebus as is.
* `sleep([number])`, where number is number of seconds to wait.
* `one_of([some phrase] | [some other phrase])` - randomly choose one of alternate phrases and then send it to messagebus
  Also, as mentioned above, it is possible to pass some input to script with `{placeholder}` syntax. 

## Examples

Quick and drity replacement for flip coin skill:
```
flip a coin:
- (please|) flip a coin
- one_of(say tails|say heads)
```

Night light automation
```
night light:
- (switch|turn) on {switch} temporarliy; turn on
- say switch on {switch} && sleep(50) && say switch off {switch}
```

