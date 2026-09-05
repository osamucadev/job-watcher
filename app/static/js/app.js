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
    actionFailed: {
      en: "Could not complete the action. Try again.",
      pt: "Não foi possível concluir a ação. Tente novamente.",
    },
  };

  const toastRegion = document.querySelector("#toast-region");

  const showToast = (message, onUndo) => {
    if (!toastRegion) return;
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.setAttribute("role", "status");

    const text = document.createElement("p");
    text.textContent = message;
    toast.appendChild(text);

    let timer;
    const dismiss = () => {
      clearTimeout(timer);
      toast.remove();
    };

    if (onUndo) {
      const undoButton = document.createElement("button");
      undoButton.type = "button";
      undoButton.className = "toast-undo";
      undoButton.textContent = MESSAGES.undo[currentLanguage()];
      undoButton.addEventListener("click", async () => {
        undoButton.disabled = true;
        try {
          await onUndo();
          window.location.reload();
        } catch (error) {
          undoButton.disabled = false;
        }
      });
      toast.appendChild(undoButton);
    }

    toastRegion.appendChild(toast);
    timer = setTimeout(dismiss, 6000);
  };

  const undoArchive = (jobId) => async () => {
    const response = await fetch(`/jobs/${jobId}/restore`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams({ return_to: window.location.pathname }),
    });
    if (!response.ok) throw new Error("restore-failed");
  };

  const removeJobRow = (jobId, kind) => {
    const row = document.querySelector(`.job-row[data-job-id="${jobId}"]`);
    const title = row ? row.dataset.jobTitle : "";
    if (row) row.remove();
    const lang = currentLanguage();
    const message = kind === "applied" ? MESSAGES.applied[lang](title) : MESSAGES.archived[lang](title);
    showToast(message, undoArchive(jobId));
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
      archiveModal.showModal();
      reasonChips()[0]?.querySelector("input")?.focus();
    };

    reasonsContainer.addEventListener("change", syncReasonStyles);

    archiveModal.addEventListener("click", (event) => {
      if (event.target === archiveModal) archiveModal.close();
      if (event.target.closest('[data-action="cancel"]')) archiveModal.close();
    });

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
        archiveModal.close();
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
      jobActionModal.showModal();
      closeButton?.focus();
    };

    jobActionModal.addEventListener("click", (event) => {
      if (event.target === jobActionModal) jobActionModal.close();
      if (event.target.closest('[data-action="close-job-action"]')) jobActionModal.close();
    });

    applyButton.addEventListener("click", async () => {
      if (!currentJob) return;
      applyButton.disabled = true;
      try {
        const response = await postArchive(currentJob.jobId, "applied", "");
        if (!response.ok) throw new Error("archive-failed");
        jobActionModal.close();
        removeJobRow(currentJob.jobId, "applied");
      } catch (error) {
        applyButton.disabled = false;
        showToast(MESSAGES.actionFailed[currentLanguage()]);
      }
    });

    archiveButton.addEventListener("click", () => {
      if (!currentJob) return;
      const job = currentJob;
      jobActionModal.close();
      openArchiveModal(job);
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

