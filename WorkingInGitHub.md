# Contributing to GPTARS_Interstellar

Welcome to the GPTARS_Interstellar community! We're excited to have you contribute code, CAD files, documentation, or related content to this project. This guide is for folks new to GitHub to help you quickly get setup to collaborate on the project.

> "Everybody good? Plenty of slaves for my robot colony?" -TARS

---

## **What You Can Contribute**
This project includes:
- **Binary CAD files** (e.g., STEP, STL)
- **Code**
- **Documentation**
- **Related content**

The primary repository is maintained by pyrater: [GPTARS_Interstellar on GitHub](https://github.com/pyrater/GPTARS_Interstellar).
Join us in discord https://discord.gg/UfQpGXPW #repo for related questions and discussions.
---

## **For Experienced GitHub Users**
- Fork the repo and submit pull requests (PRs) to [pyrater/GPTARS_Interstellar](https://github.com/pyrater/GPTARS_Interstellar).
- Notify pyrater on Discord in the `#repo` channel if your PR is ready for review.

---

## **For New Git and GitHub Users**

Never used Git or GitHub before? No problem! This section will guide you through the basic steps to get started.

### **Step 1: Create a GitHub Account**
- Sign up for a free GitHub account: [Create an account](https://docs.github.com/en/get-started/start-your-journey/creating-an-account-on-github).

### **Step 2: Fork the Repository**
1. Go to [GPTARS_Interstellar on GitHub](https://github.com/pyrater/GPTARS_Interstellar).
2. Click the **Fork** button in the top-right corner.
3. Select **Create a new fork** to make your own copy of the repository. This fork will look like `yourGithubUsername/GPTARS_Interstellar`.

Why fork? Forking allows you to make changes in your own copy of the repository without affecting the original.

### **Step 3: Install Git Locally**
If you’re new to Git, you’ll need to install it on your local machine.
- Download Git: [Git Downloads](https://git-scm.com/downloads).
- Verify the installation by running `git --version` in your command line.

### **Step 4: Secure Your GitHub Account**
- Protect your account with multi-factor authentication (MFA): [Set up MFA](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github).
- **Highly Recommended**: Set up an SSH key for secure and streamlined operations: [Generate an SSH Key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent).

### **Step 5: Clone Your Fork**
1. Open a terminal or command prompt.
2. Navigate to the folder where you want to store the repository.
3. Clone your fork:
   ```bash
   git clone git@github.com:yourGithubUsername/GPTARS_Interstellar.git
   ```
4. Navigate into the project folder:
   ```bash
   cd GPTARS_Interstellar
   ```

### **Step 6: Set Up Remotes**
- Check the remote URLs:
  ```bash
  git remote -v
  ```
  You should see your fork as `origin`.
- Add pyrater's repository as the upstream remote:
  ```bash
  git remote add upstream git@github.com:pyrater/GPTARS_Interstellar.git
  ```

Why? This setup helps you fetch updates from the main repository to keep your fork up-to-date.

---

## **Basic Git Operations**
These are the standard steps for making contributions:

### **1. Create a Branch**
Always create a new branch for your work:
```bash
git checkout -b your-branch-name
```

Branches help you isolate changes and organize features.

### **2. Make Changes**
- Add, edit, or delete files in the project.
- Use descriptive branch names, e.g., `add-new-feature` or `fix-bug`.

### **3. Stage Changes**
Stage your changes to prepare them for a commit:
```bash
git add .
```
Optionally, check the status:
```bash
git status
```

### **4. Commit Changes**
Save your changes locally with a meaningful commit message:
```bash
git commit -m "Your commit message here"
```

For non-binary files, Git tracks changes for version control. For CAD files like STL or STEP, Git stores the files as blobs without versioning.

### **5. Push Changes**
Push your branch to your fork on GitHub:
```bash
git push origin your-branch-name
```

---

## **Creating a Pull Request (PR)**
Once your changes are ready:
1. Go to pyrater's repository: [GPTARS_Interstellar](https://github.com/pyrater/GPTARS_Interstellar).
2. Click **Pull requests** in the top menu.
3. Click the green **New pull request** button.

On the **Comparing changes** page:
- **Base repository**: `pyrater/GPTARS_Interstellar`, base: `main`.
- **Head repository**: `yourGithubUsername/GPTARS_Interstellar`, compare: `your-branch-name`.

### **Provide Details**
- Add a meaningful title for your PR.
- Write a clear description of your changes, explaining what they do and why they’re needed.
- Confirm the changed files are correct.

### **Submit the PR**
- Click **Create pull request**.
- Notify pyrater on Discord in the `#repo` channel.

### **Review and Approval**
- Wait for pyrater to review your PR.
- If changes are requested, update your branch locally, commit, and push again. GitHub will automatically update the PR.
- Once approved, your changes will be merged into the main repository. Congratulations!

---

## **Keeping Your Fork Up-to-Date**
If other contributors make changes to the main repository, keep your fork in sync:
1. Fetch updates from the upstream repository:
   ```bash
   git fetch upstream
   ```
2. Merge updates into your branch:
   ```bash
   git merge upstream/main
   ```
3. Push updates to your fork:
   ```bash
   git push origin your-branch-name
   ```

---

## **Additional Resources**
- [Git Basics](https://git-scm.com/doc)
- [GitHub Docs](https://docs.github.com)
- [Common Git Commands Cheat Sheet](https://education.github.com/git-cheat-sheet-education.pdf)
- [Visual Studio Code - Working with GitHub](https://code.visualstudio.com/docs/sourcecontrol/github)

---



