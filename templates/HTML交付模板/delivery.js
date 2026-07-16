const slides = Array.from(document.querySelectorAll(".preview-slide"));
const dots = Array.from(document.querySelectorAll("[data-carousel-dot]"));
const currentSlideLabels = document.querySelectorAll("[data-current-slide]");
const slideTotalLabels = document.querySelectorAll("[data-slide-total]");
const previewScaleStages = document.querySelectorAll("[data-preview-scale-stage]");
let activeSlideIndex = 0;

function setPreviewScale(stage) {
  const target = stage.querySelector("[data-preview-scale-target]");
  if (!target) return;

  const designWidth = 360;
  const designHeight = 720;
  const availableWidth = Math.max(stage.clientWidth - 8, 1);
  const scale = Math.min(1, availableWidth / designWidth);
  stage.style.setProperty("--preview-scale", String(scale));
  stage.style.height = `${designHeight * scale}px`;
}

function selectTitleOption(titleOption) {
  document.querySelectorAll("[data-title-text]").forEach((option) => {
    const selected = option === titleOption;
    option.classList.toggle("is-active", selected);
    option.setAttribute("aria-pressed", String(selected));
  });
}

function syncSelectedTitle(titleOption) {
  const editor = titleOption?.querySelector("[data-title-editor]");
  const titleText = (editor?.innerText || titleOption?.dataset.titleText || "")
    .replace(/\s+/g, " ")
    .trim();

  if (!titleOption) return;
  titleOption.dataset.titleText = titleText;
  const copyButton = titleOption.closest(".title-choice")?.querySelector("[data-copy-text]");
  if (copyButton) copyButton.dataset.copyText = titleText;

  if (titleOption.classList.contains("is-active")) {
    document.querySelectorAll("[data-preview-title]").forEach((title) => {
      title.textContent = titleText;
    });
  }
}

function syncPreviewBody(editor) {
  const bodyText = (editor?.innerText || "").replace(/\s+/g, " ").trim();
  document.querySelectorAll("[data-preview-body]").forEach((body) => {
    body.textContent = bodyText;
  });
}

function setActiveSlide(nextIndex) {
  if (!slides.length) return;

  activeSlideIndex = (nextIndex + slides.length) % slides.length;
  slides.forEach((slide, index) => {
    slide.classList.toggle("is-active", index === activeSlideIndex);
  });
  dots.forEach((dot, index) => {
    dot.classList.toggle("is-active", index === activeSlideIndex);
  });
  currentSlideLabels.forEach((label) => {
    label.textContent = String(activeSlideIndex + 1);
  });

  const activeSlide = slides[activeSlideIndex];
  const activeImage = activeSlide?.querySelector("img");
  document.querySelectorAll(".image-thumb").forEach((thumb) => {
    const thumbImage = thumb.querySelector("img");
    thumb.classList.toggle(
      "is-active",
      Boolean(activeImage && thumbImage && activeImage.src === thumbImage.src)
    );
  });
}

slideTotalLabels.forEach((label) => {
  label.textContent = String(Math.max(slides.length, 1));
});

document.addEventListener("click", async (event) => {
  const copyTargetButton = event.target.closest("[data-copy-target]");
  const copyTextButton = event.target.closest("[data-copy-text]");

  if (copyTargetButton || copyTextButton) {
    const button = copyTargetButton || copyTextButton;
    const target = copyTargetButton
      ? document.getElementById(copyTargetButton.dataset.copyTarget)
      : null;
    const text = target?.innerText || copyTextButton?.dataset.copyText || "";
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "已复制";
    } catch (error) {
      button.textContent = "复制失败";
    }
    window.setTimeout(() => {
      button.textContent = original;
    }, 1400);
    return;
  }

  const titleOption = event.target.closest("[data-title-text]");
  if (titleOption) {
    selectTitleOption(titleOption);
    syncSelectedTitle(titleOption);
    return;
  }

  const previewTab = event.target.closest("[data-preview-tab]");
  if (previewTab) {
    const selectedPanel = previewTab.dataset.previewTab;
    document.querySelectorAll("[data-preview-tab]").forEach((tab) => {
      const selected = tab === previewTab;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", String(selected));
    });
    document.querySelectorAll("[data-preview-panel]").forEach((panel) => {
      const selected = panel.dataset.previewPanel === selectedPanel;
      panel.hidden = !selected;
      panel.classList.toggle("is-active", selected);
    });
    return;
  }

  const arrow = event.target.closest("[data-carousel-direction]");
  if (arrow) {
    const offset = arrow.dataset.carouselDirection === "next" ? 1 : -1;
    setActiveSlide(activeSlideIndex + offset);
    return;
  }

  const dot = event.target.closest("[data-carousel-dot]");
  if (dot) {
    setActiveSlide(Number(dot.dataset.carouselDot) - 1);
    return;
  }

  const imageThumb = event.target.closest("[data-editor-slide-index]");
  if (imageThumb) {
    setActiveSlide(Number(imageThumb.dataset.editorSlideIndex));
  }
});

document.addEventListener("input", (event) => {
  const titleEditor = event.target.closest("[data-title-editor]");
  if (titleEditor) {
    const titleOption = titleEditor.closest("[data-title-text]");
    selectTitleOption(titleOption);
    syncSelectedTitle(titleOption);
    return;
  }

  const postEditor = event.target.closest("[data-post-editor]");
  if (postEditor) syncPreviewBody(postEditor);
});

document.addEventListener("keydown", (event) => {
  if (event.target.closest("[contenteditable]")) return;

  if (event.key === "ArrowLeft") {
    setActiveSlide(activeSlideIndex - 1);
  }
  if (event.key === "ArrowRight") {
    setActiveSlide(activeSlideIndex + 1);
  }
});

if ("ResizeObserver" in window) {
  const previewResizeObserver = new ResizeObserver((entries) => {
    entries.forEach((entry) => setPreviewScale(entry.target));
  });
  previewScaleStages.forEach((stage) => {
    setPreviewScale(stage);
    previewResizeObserver.observe(stage);
  });
} else {
  previewScaleStages.forEach(setPreviewScale);
  window.addEventListener("resize", () => {
    previewScaleStages.forEach(setPreviewScale);
  });
}

setActiveSlide(0);
