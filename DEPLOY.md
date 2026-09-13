# Deploying to Render (free)

Hugging Face Spaces moved its Docker SDK behind a paid plan, so this deploys to
**Render's free tier** instead: 750 hours a month, no credit card, automatic
HTTPS, and a permanent URL.

## Why the app had to change first

Render's free instance gives **512 MB of RAM**. PyTorch alone is around 2 GB
installed and would be killed before the app finished starting.

So the embedding model now runs through **ONNX Runtime** (`fastembed`) instead
of PyTorch. Same MiniLM weights, same 384-dimension vectors, same retrieval
quality — but roughly 105 MB of dependencies instead of 2 GB.

Nothing else about the project changed.

---

## 1. Push the code to GitHub

Render deploys from a GitHub repo, so this comes first.

```bash
git init
git add .
git status
```

**Read the `git status` output.** These must NOT be listed: `.venv/`,
`__pycache__/`, anything containing your Groq key.

```bash
git commit -m "Service manual assistant"
git branch -M main
```

Create an empty repo at github.com/new (public, no README), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/service-manual-assistant.git
git push -u origin main
```

## 2. Create the Render service

1. Sign up at **render.com** with your GitHub account
2. **New** -> **Web Service**
3. Connect the repository you just pushed
4. Settings:
   - **Language:** Docker
   - **Branch:** main
   - **Instance type:** Free
5. **Create Web Service**

Render reads the `Dockerfile` automatically. You do not need to set a build or
start command.

## 3. Add your Groq key

In the service: **Environment** -> **Add Environment Variable**

- Key: `GROQ_API_KEY`
- Value: your key

Save. Render redeploys automatically.

Never commit the key to the repo.

## 4. Wait for the build

First build takes about 5-10 minutes, mostly installing dependencies and baking
the embedding model into the image.

When the status reads **Live**, open the URL Render gives you
(`https://your-service.onrender.com`) and upload a PDF.

---

## Things to know about the free tier

**It sleeps after 15 minutes of inactivity**, and the first request afterwards
takes up to a minute to wake it. Open the link a couple of minutes before
showing anyone.

**Uploaded documents are lost on restart**, since the index lives in process
memory. That is already noted as a limitation in the README.

**750 hours a month** is enough for one service running continuously.

---

## If the build fails

**Out of memory during build** - the Docker step that pre-downloads the model is
the heaviest part. Delete those three lines from the `Dockerfile`; the model
will download on first use instead, making the first upload slower but the
build lighter.

**Port error** - the Dockerfile reads Render's `$PORT` variable automatically.
Do not hardcode a port.

**Worker timeout on a big PDF** - the timeout is already 180 seconds. A
200-page manual on 0.1 vCPU may still exceed it; test with something smaller
first.

---

## After it is live

Put the URL in three places: the top of the README, your CV next to the
project, and your GitHub profile.
