all:help
help:
	@echo 'Read the Makefile'

IMAGE_PATH=informatimago/ccxt-test
# IMAGE_TAG=0.0
IMAGE_TAG=cpu

docker-build:
	: # Build the image:
	docker buildx ls | grep -q -s multi || docker buildx create --use --name multi
	docker buildx build --platform linux/amd64,linux/arm64 -t "$(IMAGE_PATH):$(IMAGE_TAG)" --push . 
    : # (add --push to upload to a registry like ghcr.io or Docker Hub)


# MOUNT_MODELS = --mount type=bind,source=/usr/local/share/models,target=/models,bind-recursive=enabled,readonly
# MOUNT_MODELS = -v /usr/local/share/models/llama2:/models:ro
# MOUNT_MODELS = -v /usr/local/share/models/llama2/llama-2-7b-chat.Q4_K_M.gguf:/models/llama2/llama-2-7b-chat.Q4_K_M.gguf:ro
MOUNT_MODELS = -v /usr/local/share/models/llama2:/models/llama2:ro

docker-run-on-mac:
	docker images|grep -q -s $(IMAGE_PATH) || docker pull "$(IMAGE_PATH):$(IMAGE_TAG)"
	docker run --rm -it \
		--platform linux/arm64 \
		-v ~/.apikeys:/root/.apikeys:ro \
		-v $$PWD/config-docker.yaml:/app/config.yaml:ro \
		$(MOUNT_MODELS) \
		"$(IMAGE_PATH):$(IMAGE_TAG)" $(COMMAND)

docker-run-on-linux:
	docker images|grep -q -s $(IMAGE_PATH) || docker pull "$(IMAGE_PATH):$(IMAGE_TAG)"
	docker run --rm -it \
		-v ~/.apikeys:/root/.apikeys:ro \
		-v $$PWD/config-docker.yaml:/app/config.yaml:ro \
		$(MOUNT_MODELS) \
		"$(IMAGE_PATH):$(IMAGE_TAG)" $(COMMAND)

docker-system-release:
	docker images|grep -q -s $(IMAGE_PATH) || docker pull "$(IMAGE_PATH):$(IMAGE_TAG)"
	docker run -it \
		"$(IMAGE_PATH):$(IMAGE_TAG)" \
		cat /etc/os-release

clean:
	@echo todo: delete the docker image  "$(IMAGE_PATH):$(IMAGE_TAG)"
