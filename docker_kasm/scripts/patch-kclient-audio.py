from pathlib import Path

p = Path("/kclient/index.js")
text = p.read_text()
old = """// Audio init
var audioEnabled = true;
var PulseAudio = require('pulseaudio2');
var pulse = new PulseAudio();
pulse.on('error', function(error) {
  console.log(error);
  audioEnabled = false;
  console.log('Kclient was unable to init audio, it is possible your host lacks support!!!!');
});
"""
new = """// Audio init
var audioEnabled = process.env.KCLIENT_AUDIO !== '0';
var pulse = null;
if (audioEnabled) {
  var PulseAudio = require('pulseaudio2');
  pulse = new PulseAudio();
  pulse.on('error', function(error) {
    console.log(error);
    audioEnabled = false;
    console.log('Kclient was unable to init audio, it is possible your host lacks support!!!!');
  });
}
"""
if old not in text:
    raise SystemExit('audio init block not found in /kclient/index.js')
p.write_text(text.replace(old, new, 1))
