const api = "/api";

async function updateUsers() {
  const users = await fetch(`${api}/users`).then(res => res.json());

  users.forEach(user => {
    ["username", "lender", "borrower"].forEach(id => {
      const input = document.createElement("input");
      input.type = id == "borrower" ? "checkbox" : "radio";
      input.classList.add("btn-check");
      input.name = id;
      input.value = user.name;
      input.id = `${id}-${user.name}`;
      input.required = id != "borrower";
      input.autocomplete = "off";
      document.getElementById(id).appendChild(input);

      const label = document.createElement("label");
      label.classList.add("btn", "form-control");
      label.htmlFor = `${id}-${user.name}`;
      label.textContent = user.name;
      document.getElementById(id).appendChild(label);

      if (id == "username") {
        input.addEventListener("change", e => {
          if (input.checked) {
            localStorage.setItem("username", user.name);
          }
        });

        if (localStorage.getItem("username") === user.name) {
          input.checked = true;
        }
      }
    });
  });
}

async function updateRecords() {
  const records = await fetch(`${api}/records`).then(res => res.json());

  const table = document.getElementById("tbody-records");
  if (table === null) {
    return;
  }

  [...table.rows].forEach(row => row.remove());
  Object.values(records)
    .sort((a, b) => b.created_at - a.created_at)
    .forEach(record => {
      const row = table.insertRow();
      const checkboxCell = row.insertCell();
      const checkbox = document.createElement("input");
      checkboxCell.appendChild(checkbox);
      checkbox.type = "checkbox";
      checkbox.id = `record-checkbox-${record.id}`;
      checkbox.setAttribute("x-record-id", record.id);
      ["created_at", "lender", "borrower", "amount", "remarks"].forEach(key => {
        const cell = row.insertCell();
        switch (key) {
          case "created_at":
            cell.textContent = new Date(record[key]).toLocaleString();
            break;
          case "amount":
            cell.textContent = `S$${(record[key] / 100).toFixed(2)}`;
            break;
          default:
            cell.textContent = record[key];
            break;
        }
      });
      if (!record.active) {
        checkbox.disabled = true;
        row.style.textDecoration = "line-through";
      }
    });
};

async function updateSummary() {
  const summary = await fetch(`${api}/summary`).then(res => res.json());

  const table = document.getElementById("tbody-summary");
  if (table === null) {
    return;
  }

  [...table.rows].forEach(row => row.remove());
  summary.forEach(item => {
    const row = table.insertRow();
    ["from", "to", "amount"].forEach(key => {
      const cell = row.insertCell();
      switch (key) {
        case "amount":
          cell.textContent = `S$${(item[key] / 100).toFixed(2)}`;
          break;
        default:
          cell.textContent = item[key];
          break;
      }
    });
  });
}

async function addRecord() {
  const created_by =
    document.querySelector("input[name='username']:checked")?.value;
  if (created_by === null) {
    alert("Please select a username.");
    return;
  }

  const lender = document.querySelector("input[name='lender']:checked")?.value;
  if (lender === null) {
    alert("Please select a lender.");
    return;
  }

  const borrowers = [
    ...document
      .querySelectorAll("input[name='borrower']:checked")
      ?.values() ?? []
  ]
    .map(node => node.value);
  if (borrowers.length === 0) {
    alert("Please select at least one borrower.");
    return;
  }
  if (borrowers.length === 1 && borrowers.includes(lender)) {
    alert("Lender cannot be the only borrower.");
    return;
  }

  const amount = +document.getElementById("amount").value * 100;
  if (isNaN(amount)) {
    alert("Please enter a valid amount.");
    return;
  }

  const remarks = document.getElementById("remarks").value;

  const addButton = document.getElementById("add");
  addButton.disabled = true;
  addButton.value = "Adding...";
  await fetch(`${api}/record`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: "PAYMENT", created_by, lender, borrowers, amount, remarks
    }),
  })
    .then(res => {
      alert("Record added successfully.");
      document.getElementById("form-add-record").reset();
      usernameInput.checked = true;
    })
    .catch(err => {
      alert(`Failed to add record: ${err}`);
    });
  addButton.disabled = false;
  addButton.value = "Add";
}

(() => {
  document.getElementById("form-add-record")
    .addEventListener("submit", e => {
      e.preventDefault();
      addRecord();
    });

  Object.entries({
    "nav-records-tab": updateRecords,
    "nav-summary-tab": updateSummary,
  }).forEach(([id, update]) => {
    document.getElementById(id)
      .addEventListener("shown.bs.tab", async () => {
        await update();
      });
  });
})();

(async () => {
  await Promise.all([updateRecords(), updateUsers()]);
})();
