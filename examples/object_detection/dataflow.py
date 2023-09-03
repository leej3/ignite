from typing import Any, Tuple

import albumentations as A

import numpy as np
import torch
from albumentations.pytorch.transforms import ToTensorV2
from torch.utils.data import Subset
from torchvision.datasets import VOCDetection

import ignite.distributed as idist


class Dataset(VOCDetection):
    classes = (
        "aeroplane",
        "bicycle",
        "boat",
        "bus",
        "car",
        "motorbike",
        "train",
        "bottle",
        "chair",
        "diningtable",
        "pottedplant",
        "sofa",
        "tvmonitor",
        "bird",
        "cat",
        "cow",
        "dog",
        "horse",
        "sheep",
        "person",
    )
    name_to_label = {v: k + 1 for k, v in enumerate(classes)}
    label_to_name = {v: k for k, v in name_to_label.items()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.albu_transforms = self.transforms
        self.transforms = None

    def __getitem__(self, index: int) -> Tuple[Any, Any]:
        image, annotations = super().__getitem__(index)

        image = np.asarray(image)
        annotations = annotations["annotation"]

        bboxes_classes = list(
            map(
                lambda x: (
                    int(x["bndbox"]["xmin"]),
                    int(x["bndbox"]["ymin"]),
                    int(x["bndbox"]["xmax"]),
                    int(x["bndbox"]["ymax"]),
                    x["name"],
                ),
                annotations["object"],
            )
        )
        if self.albu_transforms is not None:
            result = self.albu_transforms(image=image, bboxes=bboxes_classes)
        else:
            result = {"image": image, "bboxes": bboxes_classes}

        image, bboxes_classes = result["image"], result["bboxes"]

        bboxes = torch.tensor([a[:4] for a in bboxes_classes])
        labels = torch.tensor([self.name_to_label[a[4]] for a in bboxes_classes], dtype=torch.long)

        if bboxes.numel() == 0:
            bboxes = bboxes.reshape(0, 4)

        target = {}
        target["boxes"] = bboxes
        target["labels"] = labels
        target["image_id"] = annotations["filename"]
        assert len(bboxes.shape) == 2, (index, bboxes.shape, labels.shape, annotations["filename"])
        target["area"] = (bboxes[:, 3] - bboxes[:, 1]) * (bboxes[:, 2] - bboxes[:, 0])
        target["iscrowd"] = torch.tensor([False] * len(bboxes))

        return image, target


def default_od_collate_fn(batch):
    return tuple(zip(*batch))


def fixedsize_collate_fn(batch):
    batch = default_od_collate_fn(batch)
    images, targets = batch[0], batch[1]
    images = torch.stack(images)
    return (images, targets)


def get_train_transform(config):
    assert config["data_augs"] in ("hflip", "fixedsize")

    bbox_params = A.BboxParams(format="pascal_voc")
    if config["data_augs"] == "hflip":
        train_transform = A.Compose(
            [
                A.HorizontalFlip(p=0.5),
                A.ToFloat(256),
                ToTensorV2(),
            ],
            bbox_params=bbox_params,
        )
        return train_transform
    elif config["data_augs"] == "fixedsize":
        train_transform = A.Compose(
            [
                A.RandomScale(scale_limit=(-0.9, 1.0)),
                A.PadIfNeeded(512, 512, border_mode=0, value=(123.0, 117.0, 104.0)),
                A.RandomCrop(512, 512),
                A.HorizontalFlip(p=0.5),
                A.RandomBrightnessContrast(p=0.5),
                A.ToFloat(256),
                ToTensorV2(),
            ],
            bbox_params=bbox_params,
        )
        return train_transform

    raise ValueError()


def get_test_transform(config):
    bbox_params = A.BboxParams(format="pascal_voc")

    if config["data_augs"] == "hflip":
        return A.Compose(
            [
                A.ToFloat(256),
                ToTensorV2(),
            ],
            bbox_params=bbox_params,
        )

    elif config["data_augs"] == "fixedsize":
        test_transform = A.Compose(
            [
                A.PadIfNeeded(512, 512, border_mode=0, value=(123.0, 117.0, 104.0)),
                A.ToFloat(256),
                ToTensorV2(),
            ],
            bbox_params=bbox_params,
        )
        return test_transform

    raise ValueError()


def get_dataloader(mode, config, train_eval_size=None):
    assert mode in ["train", "train_eval", "eval"]

    if mode in ["eval", "train_eval"]:
        transform = get_test_transform(config)
        image_set = "val"
    else:
        transform = get_train_transform(config)
        image_set = "train"

    dataset = Dataset(config["data_path"], image_set=image_set, download=False, transforms=transform)

    if mode == "train_eval" and train_eval_size is not None:
        g = torch.Generator().manual_seed(len(dataset))
        train_eval_indices = torch.randperm(len(dataset), generator=g)[:train_eval_size]
        dataset = Subset(dataset, train_eval_indices)

    collate_fn = default_od_collate_fn
    # if config["data_augs"] == "fixedsize":
    #     collate_fn = fixedsize_collate_fn

    if config["eval_batch_size"] is None:
        config["eval_batch_size"] = 2 * config["batch_size"]

    data_loader = idist.auto_dataloader(
        dataset,
        batch_size=config["batch_size"] if mode == "train" else config["eval_batch_size"],
        num_workers=config["num_workers"],
        shuffle=True if mode == "train" else False,
        drop_last=True if mode == "train" else False,
        collate_fn=collate_fn,
    )

    return data_loader


def get_dataflow(config):
    train_loader = get_dataloader("train", config)
    val_loader = get_dataloader("eval", config)

    if 10 * len(val_loader.dataset) < len(train_loader.dataset):
        train_eval_size = len(val_loader)
    else:
        train_eval_size = None

    train_eval_loader = get_dataloader("train_eval", config, train_eval_size=train_eval_size)
    num_classes = len(Dataset.classes)
    return train_loader, train_eval_loader, val_loader, num_classes


def test_dataloader(dataloader, n=50):
    manual_seed(123)

    dataloader_iter = iter(dataloader)

    for j in range(n):
        try:
            imgs, targets = next(dataloader_iter)
        except Exception as e:
            print(f"Exception in batch {j}")
            raise e

        assert isinstance(imgs, list) and len(imgs) == dataloader.batch_size, (j, imgs)
        assert isinstance(targets, list) and len(targets) == dataloader.batch_size, (j, targets)

        for i, (img, target) in enumerate(zip(imgs, targets)):
            assert img.shape[0] == 3 and img.shape[1] > 50 and img.shape[2] > 50, (j, i, img.shape)
            assert img.is_floating_point()

            for key in ["boxes", "labels", "image_id"]:
                assert key in target, (j, i, target.keys())

            boxes = target["boxes"]
            assert len(boxes.shape) == 2 and boxes.shape[1] == 4, (j, i, boxes.shape, boxes.dtype)
            assert boxes.shape[0] >= 0, (j, i, boxes.shape, boxes.dtype)
            assert boxes.is_floating_point(), (j, i, boxes.shape, boxes.dtype)

            labels = target["labels"]
            assert len(labels.shape) == 1 and labels.shape[0] >= 0, (j, i, labels.shape, labels.dtype)
            assert labels.dtype == torch.long, (j, i, labels.shape, labels.dtype)

            image_id = target["image_id"]
            assert isinstance(image_id, str), (j, i, image_id)


if __name__ == "__main__":
    # Dataflow tests
    import sys
    from pathlib import Path

    assert len(sys.argv) == 3, "Usage: python dataflow.py /data hflip"
    data_path = Path(sys.argv[1])
    data_augs = sys.argv[2]
    assert data_path.exists()

    config = {
        "data_path": data_path,
        "data_augs": data_augs,
        "num_workers": 0,
        "batch_size": 8,
        "eval_batch_size": 8
    }

    from ignite.utils import manual_seed

    train_loader, train_eval_loader, val_loader, num_classes = get_dataflow(config)
    assert num_classes == 20

    test_dataloader(train_loader, n=100)
    test_dataloader(train_eval_loader, n=100)
    test_dataloader(val_loader, n=100)
