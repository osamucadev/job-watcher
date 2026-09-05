(() => {
  const storageKey = "job-watcher-language";
  const select = document.querySelector("#language");

  const applyLanguage = (language) => {
    const activeLanguage = language === "pt" ? "pt" : "en";
    document.documentElement.lang = activeLanguage === "pt" ? "pt-BR" : "en";
    document.documentElement.dataset.language = activeLanguage;

    document.querySelectorAll("[data-en][data-pt]").forEach((element) => {
      element.textContent = element.dataset[activeLanguage];
    });

    document.querySelectorAll("[data-placeholder-en][data-placeholder-pt]").forEach((element) => {
      element.placeholder = element.dataset[`placeholder${activeLanguage === "pt" ? "Pt" : "En"}`];
    });

    document.querySelectorAll("time[datetime]").forEach((element) => {
      const date = new Date(element.dateTime);
      if (!Number.isNaN(date.valueOf())) {
        element.textContent = new Intl.DateTimeFormat(activeLanguage === "pt" ? "pt-BR" : "en-US", {
          dateStyle: "medium",
          timeStyle: "short",
        }).format(date);
      }
    });

    if (select) select.value = activeLanguage;
  };

  const savedLanguage = localStorage.getItem(storageKey) || "en";
  applyLanguage(savedLanguage);

  select?.addEventListener("change", (event) => {
    const language = event.target.value;
    localStorage.setItem(storageKey, language);
    applyLanguage(language);
  });
})();

(() => {
  const currentLanguage = () => (document.documentElement.dataset.language === "pt" ? "pt" : "en");

  const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const prefersReducedMotion = () => reducedMotionQuery.matches;

  // Runs `apply` after two animation frames so the browser paints the
  // "before" state first; without this, adding the class immediately after
  // the element becomes visible skips straight to the "after" state.
  const nextFrame = (apply) => {
    requestAnimationFrame(() => requestAnimationFrame(apply));
  };

  const MESSAGES = {
    archived: {
      en: (title) => `${title} archived.`,
      pt: (title) => `${title} arquivada.`,
    },
    applied: {
      en: (title) => `${title} marked as Applied.`,
      pt: (title) => `${title} marcada como Já me candidatei.`,
    },
    undo: { en: "Undo", pt: "Desfazer" },
    close: { en: "Close", pt: "Fechar" },
    actionFailed: {
      en: "Could not complete the action. Try again.",
      pt: "Não foi possível concluir a ação. Tente novamente.",
    },
  };

  const MODAL_MOTION_MS = 180;
  const TOAST_MOTION_MS = 220;
  const TOAST_DURATION_MS = 5000;
  const ROW_LEAVE_PHASE_MS = 180;
  const ROW_COLLAPSE_PHASE_MS = 220;
  const ROW_ENTER_MS = 240;

  const openDialogAnimated = (dialog) => {
    dialog.showModal();
    if (prefersReducedMotion()) {
      dialog.classList.add("is-open");
      return;
    }
    dialog.classList.remove("is-open");
    nextFrame(() => dialog.classList.add("is-open"));
  };

  const closeDialogAnimated = (dialog) => {
    if (!dialog.open) return;
    dialog.classList.remove("is-open");
    if (prefersReducedMotion()) {
      dialog.close();
      return;
    }
    window.setTimeout(() => {
      if (!dialog.classList.contains("is-open")) dialog.close();
    }, MODAL_MOTION_MS);
  };

  const wireDialogDismissal = (dialog, { onCancelClick, onOverlayClick } = {}) => {
    dialog.addEventListener("cancel", (event) => {
      // Escape triggers the native "cancel" event, which would otherwise
      // close the dialog instantly with no exit animation.
      event.preventDefault();
      closeDialogAnimated(dialog);
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        onOverlayClick?.();
        closeDialogAnimated(dialog);
      } else if (event.target.closest("[data-action='cancel'], [data-action='close-job-action']")) {
        onCancelClick?.();
        closeDialogAnimated(dialog);
      }
    });
  };

  const toastRegion = document.querySelector("#toast-region");

  const showToast = (message, options = {}) => {
    if (!toastRegion) return;
    const { onUndo, onUndoSuccess } = options;

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.setAttribute("role", "status");

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "toast-close";
    closeButton.setAttribute("aria-label", MESSAGES.close[currentLanguage()]);
    closeButton.innerHTML = '<span aria-hidden="true">&times;</span>';
    toast.appendChild(closeButton);

    const body = document.createElement("div");
    body.className = "toast-body";
    const text = document.createElement("p");
    text.textContent = message;
    body.appendChild(text);
    toast.appendChild(body);

    const progress = document.createElement("div");
    progress.className = "toast-progress";
    toast.appendChild(progress);

    let timerId = null;
    let remaining = TOAST_DURATION_MS;
    let startedAt = null;
    let isHovered = false;
    let isFocused = false;

    const startTimer = () => {
      if (timerId !== null) return;
      startedAt = Date.now();
      timerId = window.setTimeout(dismiss, remaining);
      toast.classList.remove("is-paused");
    };

    const pauseTimer = () => {
      if (timerId === null) return;
      window.clearTimeout(timerId);
      timerId = null;
      remaining -= Date.now() - startedAt;
      toast.classList.add("is-paused");
    };

    const syncPauseState = () => {
      if (isHovered || isFocused) pauseTimer();
      else startTimer();
    };

    function dismiss() {
      if (timerId !== null) {
        window.clearTimeout(timerId);
        timerId = null;
      }
      toast.classList.remove("is-open");
      toast.classList.add("is-leaving");
      if (prefersReducedMotion()) {
        toast.remove();
        return;
      }
      window.setTimeout(() => toast.remove(), TOAST_MOTION_MS);
    }

    toast.addEventListener("mouseenter", () => {
      isHovered = true;
      syncPauseState();
    });
    toast.addEventListener("mouseleave", () => {
      isHovered = false;
      syncPauseState();
    });
    toast.addEventListener("focusin", () => {
      isFocused = true;
      syncPauseState();
    });
    toast.addEventListener("focusout", () => {
      isFocused = false;
      syncPauseState();
    });

    closeButton.addEventListener("click", dismiss);

    if (onUndo) {
      const undoButton = document.createElement("button");
      undoButton.type = "button";
      undoButton.className = "toast-undo";
      undoButton.textContent = MESSAGES.undo[currentLanguage()];
      undoButton.addEventListener("click", async () => {
        pauseTimer();
        undoButton.disabled = true;
        try {
          await onUndo();
          onUndoSuccess?.();
          dismiss();
        } catch (error) {
          undoButton.disabled = false;
          syncPauseState();
        }
      });
      body.appendChild(undoButton);
    }

    toastRegion.appendChild(toast);
    nextFrame(() => toast.classList.add("is-open"));
    startTimer();
  };

  const undoArchive = (jobId) => async () => {
    const response = await fetch(`/jobs/${jobId}/restore`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams({ return_to: window.location.pathname }),
    });
    if (!response.ok) throw new Error("restore-failed");
  };

  // Finds where `row` belongs among its siblings, mirroring the server's
  // "is_new DESC, first_seen_at DESC" ordering, so an undone job reappears
  // in roughly the right spot instead of always at the top or bottom.
  const findInsertionPoint = (list, row) => {
    const isNew = row.classList.contains("is-new");
    const rowTime = row.querySelector("time")?.getAttribute("datetime") || "";
    const siblings = Array.from(list.querySelectorAll(".job-row"));
    for (const sibling of siblings) {
      const siblingIsNew = sibling.classList.contains("is-new");
      if (isNew && !siblingIsNew) return sibling;
      if (isNew === siblingIsNew) {
        const siblingTime = sibling.querySelector("time")?.getAttribute("datetime") || "";
        if (rowTime > siblingTime) return sibling;
      }
    }
    return null;
  };

  // If archiving/applying just removed the last row on a paginated listing
  // page other than the first, step back one page instead of leaving the
  // user stranded on a now-empty page.
  const stepBackAPageIfEmpty = () => {
    if (document.querySelectorAll(".job-row").length > 0) return;
    const url = new URL(window.location.href);
    const currentPage = parseInt(url.searchParams.get("page") || "1", 10);
    if (currentPage > 1) {
      url.searchParams.set("page", String(currentPage - 1));
      window.location.href = url.toString();
    }
  };

  const animateRowRemoval = (row) => {
    if (!row) return;
    if (prefersReducedMotion()) {
      row.remove();
      stepBackAPageIfEmpty();
      return;
    }
    const startHeight = row.offsetHeight;
    row.style.height = `${startHeight}px`;
    row.style.overflow = "hidden";
    row.offsetHeight; // eslint-disable-line no-unused-expressions -- force reflow before animating
    row.classList.add("is-leaving");
    window.setTimeout(() => {
      row.classList.add("is-collapsing");
      row.style.height = "0px";
      window.setTimeout(() => {
        row.remove();
        stepBackAPageIfEmpty();
      }, ROW_COLLAPSE_PHASE_MS);
    }, ROW_LEAVE_PHASE_MS);
  };

  const animateRowInsertion = (row) => {
    if (!row) return;
    const list = document.querySelector(".job-list");
    if (!list) return;

    row.classList.remove("is-leaving", "is-collapsing");
    row.style.height = "";
    row.style.overflow = "";

    const animate = !prefersReducedMotion();
    // Add the "before" state while the row is still detached, so its first
    // rendered frame is already faded out; adding it after insertion would
    // instead animate FROM the default visible state, flashing backwards.
    if (animate) row.classList.add("is-entering");

    list.querySelector(".empty-state")?.remove();
    const insertBefore = findInsertionPoint(list, row);
    if (insertBefore) list.insertBefore(row, insertBefore);
    else list.appendChild(row);

    if (!animate) return;

    const targetHeight = row.offsetHeight;
    row.style.height = "0px";
    row.style.overflow = "hidden";
    row.offsetHeight; // eslint-disable-line no-unused-expressions -- force reflow before animating
    nextFrame(() => {
      row.style.height = `${targetHeight}px`;
      row.classList.remove("is-entering");
      window.setTimeout(() => {
        row.style.height = "";
        row.style.overflow = "";
      }, ROW_ENTER_MS);
    });
  };

  const removeJobRow = (jobId, kind) => {
    const row = document.querySelector(`.job-row[data-job-id="${jobId}"]`);
    const title = row ? row.dataset.jobTitle : "";
    animateRowRemoval(row);
    const lang = currentLanguage();
    const message = kind === "applied" ? MESSAGES.applied[lang](title) : MESSAGES.archived[lang](title);
    showToast(message, {
      onUndo: undoArchive(jobId),
      onUndoSuccess: () => animateRowInsertion(row),
    });
  };

  const postArchive = (jobId, reason, note) =>
    fetch(`/jobs/${jobId}/archive`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams({ reason, note: note || "", return_to: window.location.pathname }),
    });

  document.addEventListener("click", async (event) => {
    const trigger = event.target.closest(".js-quick-archive");
    if (!trigger || trigger.disabled) return;
    trigger.disabled = true;
    const jobId = trigger.dataset.jobId;
    try {
      const response = await postArchive(jobId, trigger.dataset.reason, "");
      if (!response.ok) throw new Error("archive-failed");
      removeJobRow(jobId, "applied");
    } catch (error) {
      trigger.disabled = false;
      showToast(MESSAGES.actionFailed[currentLanguage()]);
    }
  });

  // Archive modal: reason chips (radio group), note, confirm/cancel.
  const archiveModal = document.querySelector("#archive-modal");
  let openArchiveModal = () => {};
  if (archiveModal) {
    const subject = archiveModal.querySelector("#archive-modal-subject");
    const reasonsContainer = archiveModal.querySelector("#archive-modal-reasons");
    const noteField = archiveModal.querySelector("#archive-modal-note");
    const errorText = archiveModal.querySelector("#archive-modal-error");
    const validationText = archiveModal.querySelector("#archive-modal-validation");
    const confirmButton = archiveModal.querySelector("#archive-modal-confirm");
    const form = archiveModal.querySelector("#archive-modal-form");
    let activeJob = null;

    const reasonChips = () => Array.from(reasonsContainer.querySelectorAll(".reason-chip"));

    const syncReasonStyles = () => {
      reasonChips().forEach((chip) => {
        chip.classList.toggle("is-selected", chip.querySelector("input").checked);
      });
    };

    const resetArchiveModal = () => {
      reasonsContainer.querySelectorAll('input[name="reason"]').forEach((input) => {
        input.checked = false;
      });
      syncReasonStyles();
      noteField.value = "";
      errorText.hidden = true;
      validationText.hidden = true;
      confirmButton.disabled = false;
    };

    openArchiveModal = (job) => {
      activeJob = job;
      subject.textContent = `${job.title} — ${job.company}`;
      resetArchiveModal();
      openDialogAnimated(archiveModal);
      reasonChips()[0]?.querySelector("input")?.focus();
    };

    reasonsContainer.addEventListener("change", syncReasonStyles);

    wireDialogDismissal(archiveModal);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const selected = reasonsContainer.querySelector('input[name="reason"]:checked');
      if (!selected) {
        validationText.hidden = false;
        reasonChips()[0]?.querySelector("input")?.focus();
        return;
      }
      confirmButton.disabled = true;
      errorText.hidden = true;
      validationText.hidden = true;
      try {
        const response = await postArchive(activeJob.jobId, selected.value, noteField.value);
        if (!response.ok) throw new Error("archive-failed");
        closeDialogAnimated(archiveModal);
        removeJobRow(activeJob.jobId, "archived");
      } catch (error) {
        errorText.hidden = false;
        confirmButton.disabled = false;
      }
    });

    document.addEventListener("click", (event) => {
      const trigger = event.target.closest(".js-open-archive-modal");
      if (!trigger) return;
      const row = trigger.closest(".job-row");
      openArchiveModal({
        jobId: trigger.dataset.jobId,
        title: row?.dataset.jobTitle || "",
        company: row?.dataset.companyName || "",
      });
    });
  }

  // Job action modal: opens right after "Open job", offers Applied / Archive / Keep active.
  const jobActionModal = document.querySelector("#job-action-modal");
  let openJobActionModal = () => {};
  if (jobActionModal) {
    const subject = jobActionModal.querySelector("#job-action-modal-subject");
    const applyButton = jobActionModal.querySelector("#job-action-apply");
    const archiveButton = jobActionModal.querySelector("#job-action-archive");
    const closeButton = jobActionModal.querySelector('[data-action="close-job-action"]');
    let currentJob = null;

    openJobActionModal = (job) => {
      currentJob = job;
      subject.textContent = `${job.title} — ${job.company}`;
      applyButton.disabled = false;
      openDialogAnimated(jobActionModal);
      closeButton?.focus();
    };

    wireDialogDismissal(jobActionModal);

    applyButton.addEventListener("click", async () => {
      if (!currentJob) return;
      applyButton.disabled = true;
      try {
        const response = await postArchive(currentJob.jobId, "applied", "");
        if (!response.ok) throw new Error("archive-failed");
        closeDialogAnimated(jobActionModal);
        removeJobRow(currentJob.jobId, "applied");
      } catch (error) {
        applyButton.disabled = false;
        showToast(MESSAGES.actionFailed[currentLanguage()]);
      }
    });

    archiveButton.addEventListener("click", () => {
      if (!currentJob) return;
      const job = currentJob;
      closeDialogAnimated(jobActionModal);
      // Wait for the close animation (and the real .close() call inside it)
      // to finish before opening the archive modal, so the two dialogs
      // never overlap with two stacked backdrops.
      window.setTimeout(() => openArchiveModal(job), prefersReducedMotion() ? 0 : MODAL_MOTION_MS);
    });
  }

  // "Last opened" highlight: purely client-side, keyed by job id.
  const lastOpenedKey = "job-watcher-last-opened";

  const applyLastOpened = () => {
    let lastId = null;
    try {
      lastId = localStorage.getItem(lastOpenedKey);
    } catch (error) {
      lastId = null;
    }
    document.querySelectorAll(".job-row").forEach((row) => {
      const isLast = Boolean(lastId) && row.dataset.jobId === lastId;
      row.classList.toggle("is-last-opened", isLast);
      const badge = row.querySelector(".tag-last-opened");
      if (badge) badge.hidden = !isLast;
    });
  };

  applyLastOpened();

  document.addEventListener("click", (event) => {
    const link = event.target.closest(".js-open-job");
    if (!link) return;
    const row = link.closest(".job-row");
    const jobId = link.dataset.jobId;

    try {
      localStorage.setItem(lastOpenedKey, jobId);
    } catch (error) {
      // Browser storage unavailable; the open action still proceeds normally.
    }
    fetch(`/jobs/${jobId}/visit`, { method: "POST", keepalive: true }).catch(() => {});
    applyLastOpened();

    if (row?.dataset.status === "active") {
      openJobActionModal({
        jobId,
        title: row.dataset.jobTitle || "",
        company: row.dataset.companyName || "",
      });
    }
  });
})();

