"""QLoRA fine-tune of a ~2B vision-language model for image → invoice JSON (F8).

    python -m train.lora_vlm --data train/data --out train/adapter

STATUS: written for a Kaggle T4 (16 GB, fp16, no bf16) and NOT executed when this was committed: there was no GPU. The dataset
builder (train/build_dataset.py) and the scorer (eval/run_direct.py) are tested; this script follows the standard
transformers + peft recipe for Qwen2-VL but may need version-specific fixes. The README lists the fine-tune as not run.

What it trains: the language model's attention and MLP projections (rank 16) of Qwen2-VL-2B-Instruct, loaded in 4-bit. The vision
tower stays frozen. Loss is computed on the JSON answer only, not on the prompt.
"""
import argparse
import json
from pathlib import Path

MODEL = "Qwen/Qwen2-VL-2B-Instruct"
MIN_PIXELS, MAX_PIXELS = 256 * 28 * 28, 1024 * 28 * 28  # an A4 page at 150 dpi is 2.2 MP: cap it so text stays legible but memory fits


def load_examples(data: Path, split: str) -> list[dict]:
    return [json.loads(line) for line in (data / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from PIL import Image
    from transformers import (AutoProcessor, BitsAndBytesConfig, Qwen2VLForConditionalGeneration, Trainer, TrainingArguments)

    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path(__file__).parent / "data")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "adapter")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--accum", type=int, default=8)
    args = ap.parse_args()

    processor = AutoProcessor.from_pretrained(args.model, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        args.model, torch_dtype=torch.float16, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16))
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))  # names that only the LLM has
    model.print_trainable_parameters()

    train = load_examples(args.data, "train")

    def collate(batch):
        ex = batch[0]  # one example per step; --accum builds the effective batch
        image = Image.open(args.data / ex["image"]).convert("RGB")
        prompt = processor.apply_chat_template(ex["messages"][:1], tokenize=False, add_generation_prompt=True)
        full = prompt + ex["messages"][1]["content"][0]["text"] + "<|im_end|>\n"
        enc = processor(text=[full], images=[image], return_tensors="pt")
        n_prompt = processor(text=[prompt], images=[image], return_tensors="pt")["input_ids"].shape[1]
        labels = enc["input_ids"].clone()
        labels[:, :n_prompt] = -100  # loss on the answer only
        enc["labels"] = labels
        return enc

    Trainer(
        model=model, train_dataset=train, data_collator=collate,
        args=TrainingArguments(
            output_dir=str(args.out / "checkpoints"), per_device_train_batch_size=1, gradient_accumulation_steps=args.accum,
            num_train_epochs=args.epochs, learning_rate=args.lr, lr_scheduler_type="cosine", warmup_ratio=0.03,
            fp16=True, gradient_checkpointing=True, logging_steps=10, save_strategy="no", report_to=[],
            remove_unused_columns=False, dataloader_num_workers=2),
    ).train()
    model.save_pretrained(args.out)
    processor.save_pretrained(args.out)
    print(f"adapter saved to {args.out}")


if __name__ == "__main__":
    main()
