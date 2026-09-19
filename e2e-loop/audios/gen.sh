#!/bin/bash
# Gera midias de teste PT-BR. Uso: ./gen.sh
set -u
AQUI="$(cd "$(dirname "$0")" && pwd)"
say -v Luciana -o "$AQUI/pergunta.aiff" "Oi! Vocês têm a moto C G cento e sessenta disponível?"
ffmpeg -y -loglevel error -i "$AQUI/pergunta.aiff" -c:a libopus -b:a 32k "$AQUI/pergunta.ogg"
say -v Luciana -o "$AQUI/nome.aiff" "Oi, meu nome é Gabriel, vocês têm a C G cento e sessenta?"
ffmpeg -y -loglevel error -i "$AQUI/nome.aiff" -c:a libopus -b:a 32k "$AQUI/nome.ogg"
rm -f "$AQUI/nome.aiff"
ffmpeg -y -loglevel error -f lavfi -i anullsrc=r=16000:cl=mono -t 4 -c:a libopus "$AQUI/silencio.ogg"
ffmpeg -y -loglevel error -f lavfi -i "anoisesrc=d=3:c=brown:a=0.02:r=16000" -c:a libopus "$AQUI/ruido.ogg"
ffmpeg -y -loglevel error -f lavfi -i testsrc=s=640x480:d=1 -frames:v 1 "$AQUI/foto.jpg"
rm -f "$AQUI/pergunta.aiff"
ls -la "$AQUI"
