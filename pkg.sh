git pull origin master

rm ../ai-diffusion-latest.zip

zip -r  -UN=UTF8 ../ai-diffusion-latest.zip ai_diffusion ai_diffusion.desktop
ossutil cp result.json oss://antaai/comfyui/krita/

cd ..
ossutil cp ai-diffusion-latest.zip oss://antaai/comfyui/krita/
