const api = "/api";
const currency = "{{ currency or 'USD' }}";

function showAlert(message, type = "danger") {
  const container = document.getElementById("alerts");
  container.innerHTML = "";
  const wrapper = document.createElement("div");
  wrapper.innerHTML =
    `<div class="alert alert-${type} alert-dismissible fade show" role="alert">
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"
        aria-label="Close"></button>
    </div>`;
  container.appendChild(wrapper);
}

function formatCurrency(amount) {
  return Intl.NumberFormat(navigator.language, {
    style: "currency",
    currency,
  }).format(amount);
}

let cachedUsers = null;
async function getUsers() {
  if (cachedUsers) {
    return cachedUsers;
  }
  cachedUsers = await fetch(`${api}/users`).then(res => res.json());
  return cachedUsers;
}

async function getRecords() {
  return await fetch(`${api}/records`).then(res => res.json());
}

async function getSummary() {
  return await fetch(`${api}/summary`).then(res => res.json());
}

async function updateUsers() {
  const users = await getUsers();

  ["DEBT", "PAYMENT"].forEach(recordType => {
    const input = document.createElement("input");
    input.type = "radio";
    input.classList.add("btn-check");
    input.name = "type";
    input.value = recordType;
    input.id = `type-${recordType}`;
    input.required = true;
    input.autocomplete = "off";
    if (recordType === "DEBT") {
      input.checked = true;
    }
    document.getElementById("type").appendChild(input);

    const label = document.createElement("label");
    label.classList.add("btn", "form-control");
    label.htmlFor = `type-${recordType}`;
    label.textContent = recordType;
    document.getElementById("type").appendChild(label);
  });

  users.forEach(user => {
    if (!user.active) {
      return;
    }

    ["lender", "borrower"].forEach(id => {
      const input = document.createElement("input");
      input.type = id == "borrower" ? "checkbox" : "radio";
      input.classList.add("btn-check");
      input.name = id;
      input.value = user.name;
      input.id = `${id}-${user.name}`;
      input.setAttribute("x-user-email", user.email);
      input.required = id != "borrower";
      input.autocomplete = "off";
      document.getElementById(id).appendChild(input);

      const label = document.createElement("label");
      label.classList.add("btn", "form-control");
      label.htmlFor = `${id}-${user.name}`;
      label.textContent = user.name;
      document.getElementById(id).appendChild(label);
    });
  });
}

async function updateRecords() {
  const [users, records] = await Promise.all([getUsers(), getRecords()]);
  const userMap = Object.fromEntries(
    users.map(user => [user.email, user.name]),
  );
  Object.values(records).forEach(record => {
    record.lender = userMap[record.lender] ?? record.lender;
    record.borrower = userMap[record.borrower] ?? record.borrower;
  });

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
      checkbox.setAttribute("x-record-active", record.active ? "true" : "false");
      checkbox.addEventListener("change", onRecordCheckboxChange);
      [
        "created_at",
        "type",
        "lender",
        "borrower",
        "amount",
        "remarks",
      ].forEach(key => {
        const cell = row.insertCell();
        switch (key) {
          case "created_at":
            cell.textContent = new Date(record[key]).toLocaleString();
            break;
          case "amount":
            cell.textContent = formatCurrency(record[key] / 100);
            break;
          default:
            cell.textContent = record[key];
            break;
        }
      });
      if (!record.active) {
        row.style.textDecoration = "line-through";
      }
    });
  document.getElementById("btn-activate-records").disabled = true;
  document.getElementById("btn-cancel-records").disabled = true;
};

async function updateSummary() {
  const [users, summary] = await Promise.all([getUsers(), getSummary()]);
  const userMap = Object.fromEntries(
    users.map(user => [user.email, user.name]),
  );

  const table = document.getElementById("tbody-summary");
  if (table === null) {
    return;
  }

  [...table.rows].forEach(row => row.remove());
  summary.forEach(item => {
    const row = table.insertRow();
    [
      { key: "from", value: userMap[item.from] ?? item.from },
      { key: "to", value: userMap[item.to] ?? item.to },
      { key: "amount", value: formatCurrency(item.amount / 100) },
    ].forEach(({ value }) => {
      const cell = row.insertCell();
      cell.textContent = value;
    });

    const actionCell = row.insertCell();
    const settleBtn = document.createElement("button");
    settleBtn.classList.add("btn", "btn-success", "btn-sm");
    settleBtn.textContent = "Settle";
    settleBtn.addEventListener("click", async () => {
      settleBtn.disabled = true;
      settleBtn.textContent = "Settling...";
      const response = await fetch(`${api}/records`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "PAYMENT",
          lender: item.from,
          borrowers: [item.to],
          amount: item.amount,
          remarks: "Settlement",
        }),
      });
      const data = await response.json();
      if (response.ok) {
        await updateSummary();
      } else {
        showAlert(`Failed to settle: ${data.error || response.statusText}`);
        settleBtn.disabled = false;
        settleBtn.textContent = "Settle";
      }
    });
    actionCell.appendChild(settleBtn);
  });
}

async function addRecord() {
  const type =
    document.querySelector("input[name='type']:checked")?.value;
  if (type === null) {
    showAlert("Please select a type.", "warning");
    return;
  }

  const lender =
    document.querySelector("input[name='lender']:checked")
      ?.getAttribute("x-user-email");
  if (lender === null) {
    showAlert("Please select a lender.", "warning");
    return;
  }

  const borrowers = [
    ...document
      .querySelectorAll("input[name='borrower']:checked"),
  ]
    .map(node => node.getAttribute("x-user-email"));
  if (borrowers.length === 0) {
    showAlert("Please select at least one borrower.", "warning");
    return;
  }
  if (borrowers.length === 1 && borrowers.includes(lender)) {
    showAlert("Lender cannot be the only borrower.", "warning");
    return;
  }

  const amount = +document.getElementById("amount").value * 100;
  if (isNaN(amount)) {
    showAlert("Please enter a valid amount.", "warning");
    return;
  }

  const remarks = document.getElementById("remarks").value;

  const addButton = document.getElementById("add");
  addButton.disabled = true;
  addButton.value = "Adding...";

  const response = await fetch(`${api}/records`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type, lender, borrowers, amount, remarks
    }),
  });
  const data = await response.json();
  if (response.ok) {
    showAlert("Record added successfully.", "success");
    document.getElementById("form-add-record").reset();
  } else {
    showAlert(`Failed to add record: ${data.error || response.statusText}`);
  }

  addButton.disabled = false;
  addButton.value = "Add";
}

function onRecordCheckboxChange() {
  const allBoxes = [
    ...document.querySelectorAll(
      "#tbody-records input[type='checkbox']",
    ),
  ];
  const checkedBoxes = allBoxes.filter(cb => cb.checked);

  if (checkedBoxes.length === 0) {
    allBoxes.forEach(cb => { cb.disabled = false; });
    document.getElementById("btn-activate-records").disabled = true;
    document.getElementById("btn-cancel-records").disabled = true;
    return;
  }

  const selectedActive =
    checkedBoxes[0].getAttribute("x-record-active") === "true";
  allBoxes.forEach(cb => {
    if (!cb.checked) {
      cb.disabled =
        (cb.getAttribute("x-record-active") === "true") !== selectedActive;
    }
  });
  document.getElementById("btn-activate-records").disabled = selectedActive;
  document.getElementById("btn-cancel-records").disabled = !selectedActive;
}

async function setRecordsActive(active) {
  const checked = [
    ...document.querySelectorAll(
      "#tbody-records input[type='checkbox']:checked",
    ),
  ];
  if (checked.length === 0) {
    showAlert(
      `Please select at least one record to ${active ? "activate" : "cancel"}.`,
      "warning",
    );
    return;
  }
  const ids = checked.map(cb => +cb.getAttribute("x-record-id"));
  const response = await fetch(`${api}/records/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, active }),
  });
  const data = await response.json();
  if (response.ok) {
    await updateRecords();
  } else {
    showAlert(
      `Failed to ${active ? "activate" : "cancel"} records: ` +
      `${data.error || response.statusText}`,
    );
  }
}

(() => {
  document.getElementById("input-currency-label").textContent =
    Intl.NumberFormat(navigator.language, {
      style: "currency",
      currency,
    })
      .formatToParts(0)
      .find(part => part.type === "currency")
      .value;
})();

(() => {
  document.getElementById("form-add-record")
    .addEventListener("submit", e => {
      e.preventDefault();
      addRecord();
    });

  document.getElementById("btn-activate-records")
    .addEventListener("click", () => { setRecordsActive(true); });
  document.getElementById("btn-cancel-records")
    .addEventListener("click", () => { setRecordsActive(false); });

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
