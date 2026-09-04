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

