# train_fire_segmentation.py
import os
import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms
from PIL import Image
import torch.nn as nn
import torch.optim as optim

class SimpleSegDataset(Dataset):
    def __init__(self, image_paths, mask_paths, transform=None):
        self.image_paths = image_paths
        self.mask_paths = mask_paths
        self.transform = transform

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        img = Image.open(self.image_paths[idx]).convert("RGB")
        mask = Image.open(self.mask_paths[idx]).convert("L")  # 0/1 mask
        if self.transform:
            img = self.transform(img)
            mask = transforms.ToTensor()(mask)
        mask = (mask > 0.5).float()
        return img, mask.long().squeeze(0)

def get_model(num_classes=2):
    model = models.segmentation.deeplabv3_resnet50(pretrained=True)
    model.classifier[4] = nn.Conv2d(256, num_classes, kernel_size=1)
    return model

def train_loop(train_loader, model, device, epochs=5):
    model.to(device)
    optimizer = optim.Adam(model.parameters(), lr=1e-4)
    criterion = nn.CrossEntropyLoss()
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for imgs, masks in train_loader:
            imgs = imgs.to(device)
            masks = masks.to(device)
            out = model(imgs)['out']
            loss = criterion(out, masks)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        print(f"Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(train_loader)}")
    torch.save(model.state_dict(), 'models/fire_seg_deeplab.pth')
    print("Saved segmentation model to models/fire_seg_deeplab.pth")

if __name__ == "__main__":
    # Placeholder: prepare lists of image and mask paths
    train_images = []   # fill with filepaths of satellite images
    train_masks = []    # fill with binary masks (fire=1)
    # Example transforms
    transform = transforms.Compose([
        transforms.Resize((256,256)),
        transforms.ToTensor(),
    ])
    dataset = SimpleSegDataset(train_images, train_masks, transform=transform)
    loader = DataLoader(dataset, batch_size=4, shuffle=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = get_model(num_classes=2)
    train_loop(loader, model, device, epochs=10)
