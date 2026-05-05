# Git Setup Guide for NeuralToolRouter

This guide will help you initialize Git, commit your code, and push it to a remote repository.

## Prerequisites

- Git installed on your system
- GitHub/GitLab/Bitbucket account (for remote repository)

## Step 1: Initialize Git Repository

If you haven't already initialized Git:

```bash
cd neural-tool-router
git init
```

## Step 2: Review Files to Commit

Check what files will be committed:

```bash
git status
```

The `.gitignore` file is already configured to exclude:
- Virtual environment (`venv/`)
- Environment variables (`.env`)
- Generated data files
- Model files
- Log files
- Python cache files

## Step 3: Stage All Files

Add all files to staging:

```bash
git add .
```

Or add specific files:

```bash
git add README.md
git add config.py
git add phase1_generator.py
# ... etc
```

## Step 4: Create Initial Commit

```bash
git commit -m "Initial commit: NeuralToolRouter framework

- Complete three-phase architecture
- Phase 1: Synthetic data generation
- Phase 2: Model training with contrastive learning
- Phase 3: Runtime agentic loop
- MCP integration with fallback to predefined tools
- Hybrid retrieval (BM25 + Dense)
- Comprehensive documentation
- Setup scripts for easy installation"
```

## Step 5: Create Remote Repository

### Option A: GitHub

1. Go to https://github.com/new
2. Create a new repository named `neural-tool-router`
3. **Do NOT** initialize with README, .gitignore, or license (we already have these)
4. Copy the repository URL

### Option B: GitLab

1. Go to https://gitlab.com/projects/new
2. Create a new project named `neural-tool-router`
3. Choose "Create blank project"
4. Copy the repository URL

### Option C: Bitbucket

1. Go to https://bitbucket.org/repo/create
2. Create a new repository named `neural-tool-router`
3. Copy the repository URL

## Step 6: Add Remote Repository

Replace `YOUR_USERNAME` and `YOUR_REPO_URL` with your actual values:

```bash
# For GitHub
git remote add origin https://github.com/YOUR_USERNAME/neural-tool-router.git

# For GitLab
git remote add origin https://gitlab.com/YOUR_USERNAME/neural-tool-router.git

# For Bitbucket
git remote add origin https://bitbucket.org/YOUR_USERNAME/neural-tool-router.git
```

Verify the remote was added:

```bash
git remote -v
```

## Step 7: Push to Remote Repository

### First Push (Main Branch)

```bash
# Rename branch to main (if needed)
git branch -M main

# Push to remote
git push -u origin main
```

If you encounter authentication issues:

**For HTTPS:**
```bash
# You'll be prompted for username and password/token
git push -u origin main
```

**For SSH:**
```bash
# First, set up SSH keys (if not already done)
# Then use SSH URL
git remote set-url origin git@github.com:YOUR_USERNAME/neural-tool-router.git
git push -u origin main
```

## Step 8: Verify Upload

Visit your repository URL in a browser to confirm all files were uploaded.

## Common Git Commands

### Check Status
```bash
git status
```

### View Commit History
```bash
git log
git log --oneline
```

### Create a New Branch
```bash
git checkout -b feature/new-feature
```

### Switch Branches
```bash
git checkout main
git checkout feature/new-feature
```

### Pull Latest Changes
```bash
git pull origin main
```

### Push Changes
```bash
git add .
git commit -m "Description of changes"
git push origin main
```

## Branching Strategy

We recommend following Git Flow:

- `main` - Production-ready code
- `develop` - Development branch
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Urgent fixes

Example workflow:

```bash
# Create feature branch
git checkout -b feature/add-new-retrieval

# Make changes and commit
git add .
git commit -m "Add new retrieval strategy"

# Push feature branch
git push origin feature/add-new-retrieval

# Create Pull Request on GitHub/GitLab
# After review and merge, delete feature branch
git checkout main
git pull origin main
git branch -d feature/add-new-retrieval
```

## Protecting Sensitive Data

**IMPORTANT**: Never commit sensitive data!

The `.gitignore` already excludes:
- `.env` (contains API keys)
- `*.log` (may contain sensitive logs)
- `data/` (may contain private data)

To check if sensitive files are tracked:

```bash
git ls-files | grep -E '\.env|\.log'
```

If you accidentally committed sensitive data:

```bash
# Remove from Git but keep locally
git rm --cached .env
git commit -m "Remove .env from tracking"
git push origin main

# If already pushed, consider using git-filter-branch or BFG Repo-Cleaner
# See: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
```

## Setting Up GitHub Actions (Optional)

Create `.github/workflows/tests.yml` for automated testing:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          pytest
```

## Troubleshooting

### Issue: Permission Denied (publickey)

**Solution**: Set up SSH keys or use HTTPS with personal access token

### Issue: Large Files Rejected

**Solution**: Use Git LFS for large model files:
```bash
git lfs install
git lfs track "*.pth"
git lfs track "*.pt"
git add .gitattributes
```

### Issue: Merge Conflicts

**Solution**: 
```bash
git pull origin main
# Resolve conflicts in files
git add .
git commit -m "Resolve merge conflicts"
git push origin main
```

## Additional Resources

- [Git Documentation](https://git-scm.com/doc)
- [GitHub Guides](https://guides.github.com/)
- [GitLab Documentation](https://docs.gitlab.com/)
- [Atlassian Git Tutorials](https://www.atlassian.com/git/tutorials)

## Quick Reference

```bash
# Initialize
git init
git add .
git commit -m "Initial commit"

# Connect to remote
git remote add origin <URL>
git push -u origin main

# Daily workflow
git pull origin main
# Make changes
git add .
git commit -m "Description"
git push origin main

# Branching
git checkout -b feature/name
git push origin feature/name
# Create PR, merge, then:
git checkout main
git pull origin main
git branch -d feature/name
```

---

**Ready to push your code?** Follow the steps above and your NeuralToolRouter framework will be safely stored in your Git repository!