git pull origin master
zip -r  -UN=UTF8 ../ai-diffusion-latest.zip .
ossutil cp result.json oss://antaai/comfyui/krita/

cd ..
ossutil cp ai-diffusion-latest.zip oss://antaai/comfyui/krita/
