#%%
import os
import torch
import pandas as pd
import numpy as np
from torch.utils.data import Dataset, random_split, DataLoader
from PIL import Image
import torchvision.models as models
import matplotlib.pyplot as plt
import torchvision.transforms as transforms
from sklearn.metrics import f1_score
import torch.nn.functional as F
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from torchvision.utils import make_grid
import PyQt5

%matplotlib qt
#%%

#df = pd.read_csv(r"C:\Users\claud\OneDrive\Documents\Python\btc_clean.csv",encoding = "ISO-8859-1")
df = pd.read_csv("btc_clean.csv",encoding = "ISO-8859-1")
df.head()
#%%
cols = [x for x in df.columns]
df = df.replace('\x97',np.nan)
df[cols[1:]]=df[cols[1:]].astype(float,errors='ignore')
#df[cols[0]]=df[cols[0]].astype(np.datetime64[ns]())
df = df.interpolate()
df.head()
#%%
wnd = 100
df['lows'] = df['Close'].rolling(window=wnd,center=True).min()
df['highs'] = df['Close'].rolling(window=wnd,center=True).max()

df['span'] = df['highs'] - df['lows']
df['val'] = df['Close'] - df['lows']
df['ratio'] = df['val'] / df['span'] 
df['ratio'] = df['ratio'].rolling(window=10,center=True).mean()

"""Lets limit our DataFrame to only the essential columns 
and crop out the beginning and the end which contains NaN values 
due to the rolling windows and save to numpy arrays
"""
#%%
df = df[['Open','High','Low','Close','Volume (Currency)','ratio']][55:len(df)-55].reset_index(drop=True) #wnd/2 + 5 = 55
inputs = df[['Open','High','Low','Close','Volume (Currency)']].values
targets = df['ratio'].values

len(df)
#%%
"""## Creating Datasets & Data Loaders
We can now create a dataset by using the TensorDataset Function.
As we are not working with images but with "raw" data point we 
can create our input sample with a loop. 
(maybe not the most pretty way of doing it but we only have to do it once)
In the same step we also normalize the inputs. 
As we are working with sequential Data we have to normalize 
per sample and not over the entire data set.
"""

lookback = 200
inputs_list = []
for x in range(lookback,len(inputs)):
    inp = inputs[x-lookback:x]
    inp = np.moveaxis(inp, -1, 0) # Channels should come first
    inputs_list.append(inp)

lookback = 200
targets_list = []
for x in range(lookback,len(targets)):
    target = targets[x]
    targets_list.append(target)

"""Normalization"""

inputs_normalized = []
for arr in inputs_list:
    mean = np.mean(arr, axis=1)
    var = np.std(arr,axis=1)
    means_vec = mean.reshape((5, 1))
    var_vec = var.reshape((5, 1))
    arr= arr - means_vec
    arr= arr / var_vec
    inputs_normalized.append(arr)

# inputs_normalized[0]

len(targets_list)

"""Creating the Dataset"""

batch_size= 128
tensor_x = torch.Tensor(inputs_normalized[:50000]) # transform to torch tensor 
tensor_y = torch.Tensor(targets_list[:50000]).view(-1,1)
my_dataset = TensorDataset(tensor_x,tensor_y) # create your datset

val_pct = 0.1
val_size = int(val_pct * len(my_dataset))
train_size = len(my_dataset) - val_size

train_ds, val_ds = random_split(my_dataset, [train_size, val_size])
len(train_ds), len(val_ds)

train_loader = DataLoader(train_ds, batch_size, shuffle=True, num_workers=2, pin_memory=True)
val_loader = DataLoader(val_ds, batch_size, num_workers=2, pin_memory=True)

for batch in train_loader:
  print(batch[0].size())
  print(batch[1].size())
  break
#%%
"""## Creating the Model

I have no Idea if 1D Convolutions work and how the have to be implemented so lets start with something simple
"""

class TimeSeriesBase(nn.Module):
    def training_step(self, batch):
        images, targets = batch 
        out = self(images)                      
        loss = F.l1_loss(out, targets)      
        return loss
    
    def validation_step(self, batch):
        images, targets = batch 
        out = self(images)                           # Generate predictions
        loss = F.l1_loss(out, targets)  # Calculate loss
        return {'val_loss': loss.detach() }

        
    def validation_epoch_end(self, outputs):
        batch_losses = [x['val_loss'] for x in outputs]
        epoch_loss = torch.stack(batch_losses).mean()   # Combine losses
        return {'val_loss': epoch_loss.item()}
    
    def epoch_end(self, epoch, result):
        print("Epoch [{}], train_loss: {:.4f}, val_loss: {:.4f}".format(
            epoch, result['train_loss'], result['val_loss']))

class BTCModel(TimeSeriesBase):
    def __init__(self):
        super().__init__()
        self.network = nn.Sequential(
            nn.Conv1d(5, 10, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(2),

            nn.Conv1d(10, 50, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(2),

            nn.Conv1d(50, 10, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),

            nn.Flatten(), 
            nn.Linear(10, 1)

        )
        
    def forward(self, xb):
        return self.network(xb)

model = BTCModel()
model

def get_default_device():
    """Pick GPU if available, else CPU"""
    if torch.cuda.is_available():
        return torch.device('cuda')
    else:
        return torch.device('cpu')
    
def to_device(data, device):
    """Move tensor(s) to chosen device"""
    if isinstance(data, (list,tuple)):
        return [to_device(x, device) for x in data]
    return data.to(device, non_blocking=True)

class DeviceDataLoader():
    """Wrap a dataloader to move data to a device"""
    def __init__(self, dl, device):
        self.dl = dl
        self.device = device
        
    def __iter__(self):
        """Yield a batch of data after moving it to device"""
        for b in self.dl: 
            yield to_device(b, self.device)

    def __len__(self):
        """Number of batches"""
        return len(self.dl)

device = get_default_device()
device

train_dl = DeviceDataLoader(train_loader, device)
val_dl = DeviceDataLoader(val_loader, device)
to_device(model, device)

def try_batch(dl):
    for images, labels in dl:
        print('images.shape:', images.shape)
        out = model(images)
        print('out.shape:', out.shape)
        print('out[0]:', out[0])
        break

try_batch(train_dl)

"""If your kernel runs out of memory here, you might need to reduce your batch size.

## Training the model
"""

from tqdm.notebook import tqdm

@torch.no_grad()
def evaluate(model, val_loader):
    model.eval()
    outputs = [model.validation_step(batch) for batch in val_loader]
    return model.validation_epoch_end(outputs)

def fit(epochs, lr, model, train_loader, val_loader, opt_func=torch.optim.SGD):
    torch.cuda.empty_cache()
    history = []
    optimizer = opt_func(model.parameters(), lr)
    for epoch in range(epochs):
        # Training Phase 
        model.train()
        train_losses = []
        for batch in train_loader:
            loss = model.training_step(batch)
            train_losses.append(loss)
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
        # Validation phase
        result = evaluate(model, val_loader)
        result['train_loss'] = torch.stack(train_losses).mean().item()
        model.epoch_end(epoch, result)
        history.append(result)
    return history

model = to_device(model, device)

evaluate(model, val_dl)

num_epochs = 10
opt_func = torch.optim.Adam
lr = 1e-5

history = fit(num_epochs, lr, model, train_dl, val_dl, opt_func)

"""## Making predictions 

create the test set
"""

batch_size= 128
test_x = torch.Tensor(inputs_normalized[50000:]) # transform to torch tensor 
test_y = torch.Tensor(targets_list[50000:]).view(-1,1)
test_set = TensorDataset(test_x,test_y) # create your datset

len(test_set)

test_dl = DeviceDataLoader(DataLoader(test_set, batch_size, num_workers=2, pin_memory=True), device)

@torch.no_grad()
def predict_dl(dl, model):
    torch.cuda.empty_cache()
    batch_probs = []
    for xb, _ in tqdm(dl):
        probs = model(xb)
        batch_probs.append(probs.cpu().detach())
    batch_probs = torch.cat(batch_probs)
    return batch_probs

test_preds = predict_dl(test_dl, model)
len(test_preds)

test_preds.size()

test_df = df[50200:]
len(test_df)

"""maping the predinctions to the orignial dataframe"""

test_df['preds']= test_preds[:,0]



fig, (ax1,ax2) = plt.subplots(2,1,sharex=True)
ax1.plot(test_df['Close'])
ax2.plot(test_df['preds'])