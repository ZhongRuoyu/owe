const api = "/api";
const currency = "{{ currency or 'USD' }}";

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
        checkbox.disabled = true;
        row.style.textDecoration = "line-through";
      }
    });
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
        alert(`Failed to settle: ${data.error || response.statusText}`);
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
    alert("Please select a type.");
    return;
  }

  const lender =
    document.querySelector("input[name='lender']:checked")
      ?.getAttribute("x-user-email");
  if (lender === null) {
    alert("Please select a lender.");
    return;
  }

  const borrowers = [
    ...document
      .querySelectorAll("input[name='borrower']:checked"),
  ]
    .map(node => node.getAttribute("x-user-email"));
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

  const response = await fetch(`${api}/records`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type, lender, borrowers, amount, remarks
    }),
  });
  const data = await response.json();
  if (response.ok) {
    alert("Record added successfully.");
    document.getElementById("form-add-record").reset();
  } else {
    alert(`Failed to add record: ${data.error || response.statusText}`);
  }

  addButton.disabled = false;
  addButton.value = "Add";
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
