"""Explicit memory-layout policy for Qwen3's BF16 patch Conv3D."""


def configure_patch_embed_memory_format(model, memory_format: str = "native") -> None:
    if memory_format == "native":
        return
    if memory_format != "channels_last_3d":
        raise ValueError(f"Unsupported patch embedding memory format: {memory_format}")
    import torch

    # Keep tensor values and the Conv3D operation; change only weight strides.
    # PyTorch can then select its cuDNN channels-last BF16 convolution path.
    model.model.visual.patch_embed.proj.to(memory_format=torch.channels_last_3d)
