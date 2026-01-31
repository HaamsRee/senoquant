# Installation

SenoQuant targets Python 3.11 and is designed to run inside a napari environment.

## 1. Install Miniconda (if you don't have conda)

If you don't have conda or don't know what it is, you need to install **Miniconda** first. Miniconda is a lightweight Python environment manager that makes it easy to install SenoQuant and its dependencies. Follow the instructions for your operating system below.
> An environment isolates programs and their dependencies from each other, preventing conflicts.

### Windows

1. Visit the **Miniconda installation page**: https://www.anaconda.com/docs/getting-started/miniconda/install. Follow the instructions for Windows and download the Miniconda Graphical Installer.
    > **Why Miniconda and not Anaconda?**  
    Miniconda is a lightweight alternative to the full Anaconda distribution. It includes only the essential package manager and Python, using significantly less disk space and fewer system resources. This makes it ideal for most users.

2. Open the downloaded `.exe` file (it should be in your **Downloads** folder)
3. Click **"Next >"** to start the installation wizard
4. Read the license and click **"I Agree"**
5. Choose **"Just Me"** (recommended) and click **"Next >"**
6. Keep the default installation location and click **"Next >"**
7. On the "Advanced Options" screen:
   - Check the box: **"Register Miniconda3 as my default Python 3.xx"**
   - Check the box: **"Clear the package cache upon completion"**
   > We recommend **not** checking the box: **"Add installation to my PATH environment variable"** to avoid potential conflicts with other applications.
   - Click **"Install"**
8. Wait for the installation to complete, then click **"Next >"** and **"Finish"**
9. Use the Start Menu to open the **Anaconda Prompt** (search for "Anaconda Prompt")
10. In the Anaconda Prompt, type the following command to initialize conda for your shell(s):
    ```bash
    conda init
    ```
    > This step ensures that you can access conda from any command prompt or PowerShell window, and not just the Anaconda Prompt.

**To verify it worked:**
- Use the Start Menu to open a new **Command Prompt** or **PowerShell** window
- Type: `conda --version`
- If you see a version number like `conda xx.x.x`, you're ready to proceed.

### macOS

**Under construction**

### Linux

**Under construction**

## 2. Create an environment
In your terminal (Command Prompt/PowerShell on Windows, Terminal on macOS/Linux), create and activate a new conda environment with Python 3.11.  
Copy and paste the following command into your terminal:

```bash
conda create -n senoquant python=3.11
```

Hit Enter.
When prompted to proceed, type `y` and press Enter.  
Next, activate the environment:

```bash
conda activate senoquant
```

You should see `(senoquant)` at the beginning of your terminal prompt, indicating that the environment is active.

## 3. Install UV and napari

We strongly recommend using `uv` instead of `pip` because standard pip often has difficulty solving complex dependencies. `uv` is also *much* faster.

```bash
pip install uv
uv pip install "napari[all]"
```

Alternatively, using standard `pip`:

```bash
pip install "napari[all]"
```

## 4. Install SenoQuant

```bash
uv pip install senoquant
```

Alternatively, using standard `pip` (not recommended. This might be fine for napari, but often fails for SenoQuant):

```bash
pip install senoquant
```

Model files are downloaded automatically on first use from Hugging Face.

> The first launch of napari and the SenoQuant plugin will be slower as napari initializes and SenoQuant downloads model files (a few GBs) from Hugging Face. Subsequent launches will be faster as models are cached locally.

### Optional dependencies

- `uv pip install senoquant[gpu]` for GPU acceleration of the RMP spot detector (requires CUDA; Windows and Linux only).
- `uv pip install senoquant[all]` for full stack.

## 5. Launch

Start napari from your terminal:

```bash
napari
```
> Make sure the terminal remains open while using napari to keep it running. The terminal also displays useful info/warning/error messages.

Then select `Plugins` -> `SenoQuant` to launch SenoQuant.
