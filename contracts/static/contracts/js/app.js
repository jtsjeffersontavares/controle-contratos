(() => {
  const button = document.querySelector('[data-menu-button]');
  const sidebar = document.querySelector('[data-sidebar]');
  if (button && sidebar) {
    button.addEventListener('click', () => sidebar.classList.toggle('open'));
  }
  document.querySelectorAll('.message').forEach((message) => {
    window.setTimeout(() => message.classList.add('fade'), 7000);
  });

  const deliveryFormset = document.querySelector('[data-delivery-formset]');
  if (deliveryFormset) {
    const body = deliveryFormset.querySelector('[data-delivery-formset-body]');
    const template = deliveryFormset.querySelector('[data-delivery-form-template]');
    const addButton = deliveryFormset.querySelector('[data-delivery-form-add]');
    const totalFormsInput = deliveryFormset.querySelector('input[name="delivery_locations-TOTAL_FORMS"]');

    const markForDeletion = (row) => {
      const deleteInput = row.querySelector('input[name$="-DELETE"]');
      if (deleteInput) {
        deleteInput.checked = true;
      }
      row.hidden = true;
    };

    const bindRemoveButtons = (scope) => {
      scope.querySelectorAll('[data-delivery-form-remove]').forEach((removeButton) => {
        removeButton.addEventListener('click', () => {
          const row = removeButton.closest('[data-delivery-form-row]');
          if (row) {
            markForDeletion(row);
          }
        });
      });
    };

    const addForm = () => {
      if (!template || !body || !totalFormsInput) return;
      const formIndex = Number.parseInt(totalFormsInput.value, 10);
      const fragment = template.innerHTML.replaceAll(/__prefix__/g, String(formIndex));
      body.insertAdjacentHTML('beforeend', fragment);
      totalFormsInput.value = String(formIndex + 1);
      bindRemoveButtons(body);
    };

    bindRemoveButtons(body);
    addButton?.addEventListener('click', addForm);
  }
})();
