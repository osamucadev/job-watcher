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

  const modal = document.querySelector("#archive-modal");
  if (modal) {
    const subject = modal.querySelector("#archive-modal-subject");
    const reasonSelect = modal.querySelector("#archive-modal-reason");
    const noteField = modal.querySelector("#archive-modal-note");
    const errorText = modal.querySelector("#archive-modal-error");
    const confirmButton = modal.querySelector("#archive-modal-confirm");
    const form = modal.querySelector("#archive-modal-form");
    let activeJobId = null;

    const resetModal = () => {
      reasonSelect.value = "";
      noteField.value = "";
      errorText.hidden = true;
      confirmButton.disabled = false;
    };

    document.addEventListener("click", (event) => {
      const trigger = event.target.closest(".js-open-archive-modal");
      if (!trigger) return;
      const row = trigger.closest(".job-row");
      activeJobId = trigger.dataset.jobId;
      subject.textContent = row ? `${row.dataset.jobTitle} — ${row.dataset.companyName}` : "";
      resetModal();
      modal.showModal();
      reasonSelect.focus();
    });

    modal.addEventListener("click", (event) => {
      if (event.target === modal) modal.close();
      if (event.target.closest('[data-action="cancel"]')) modal.close();
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!reasonSelect.value) {
        reasonSelect.reportValidity();
        return;
      }
      confirmButton.disabled = true;
      errorText.hidden = true;
      try {
        const response = await postArchive(activeJobId, reasonSelect.value, noteField.value);
        if (!response.ok) throw new Error("archive-failed");
        modal.close();
        removeJobRow(activeJobId, "archived");
      } catch (error) {
        errorText.hidden = false;
        confirmButton.disabled = false;
      }
    });
  }

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
    const jobId = link.dataset.jobId;
    try {
      localStorage.setItem(lastOpenedKey, jobId);
    } catch (error) {
      // Browser storage unavailable; the open action still proceeds normally.
    }
    fetch(`/jobs/${jobId}/visit`, { method: "POST", keepalive: true }).catch(() => {});
    applyLastOpened();
  });
})();

