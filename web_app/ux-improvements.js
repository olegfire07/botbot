// UX Improvements - Priority 1

// 1. Validation with error highlighting
function validateField(field, errorMessage) {
    const errorDiv = field.nextElementSibling;

    if (!field.validity.valid) {
        field.classList.add('input-error');
        if (errorDiv && errorDiv.classList.contains('error-message')) {
            errorDiv.textContent = errorMessage;
            errorDiv.classList.add('show');
        }
        return false;
    } else {
        field.classList.remove('input-error');
        if (errorDiv && errorDiv.classList.contains('error-message')) {
            errorDiv.classList.remove('show');
        }
        return true;
    }
}

function clearFieldError(field) {
    field.classList.remove('input-error');

    // Try to find error message in next sibling
    let errorDiv = field.nextElementSibling;

    // If not found or not an error message, try finding it within the parent container
    if (!errorDiv || !errorDiv.classList.contains('error-message')) {
        const parent = field.closest('.input-wrapper') || field.parentElement;
        if (parent) {
            errorDiv = parent.querySelector('.error-message');
        }
    }

    if (errorDiv && errorDiv.classList.contains('error-message')) {
        errorDiv.classList.remove('show');
    }
}

// Validate ticket number (exactly 11 digits)
function validateTicket(input) {
    const value = input.value.replace(/\D/g, '');
    if (value.length !== 11) {
        return validateField(input, 'Введите ровно 11 цифр');
    }
    return validateField(input, '');
}

// Format number with spaces (15000 -> 15 000)
function formatNumberWithSpaces(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

// Input mask for evaluation field
function formatEvaluation(input) {
    let value = input.value.replace(/\D/g, '');
    if (value) {
        input.value = formatNumberWithSpaces(value);
    }
}

// Scroll to first error
function scrollToFirstError() {
    const firstError = document.querySelector('.input-error');
    if (firstError) {
        firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
        firstError.focus();
    }
}

// Enhanced validation before submit
function validateForm() {
    let isValid = true;
    const errors = [];

    // Validate department
    const dept = document.getElementById('department');
    if (!dept.value || dept.value.length === 0) {
        validateField(dept, 'Укажите подразделение');
        isValid = false;
        errors.push(dept);
    }

    // Validate issue
    const issue = document.getElementById('issue');
    if (!issue.value || issue.value.length === 0) {
        validateField(issue, 'Укажите номер заключения');
        isValid = false;
        errors.push(issue);
    }

    // Validate ticket (11 digits)
    const ticket = document.getElementById('ticket');
    if (!validateTicket(ticket)) {
        isValid = false;
        errors.push(ticket);
    }

    // Validate items
    const items = document.querySelectorAll('.item-card');
    items.forEach((item, idx) => {
        const desc = item.querySelector('.desc');
        const eval_field = item.querySelector('.eval');

        if (!desc.value) {
            validateField(desc, 'Введите описание предмета');
            isValid = false;
            errors.push(desc);
        }

        if (!eval_field.value) {
            validateField(eval_field, 'Введите оценку');
            isValid = false;
            errors.push(eval_field);
        }
    });

    if (!isValid && errors.length > 0) {
        errors[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
        errors[0].focus();
    }

    return isValid;
}

// Remove highlight while the user is editing the field
document.addEventListener('input', function (e) {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.matches('input, select, textarea')) {
        clearFieldError(target);
    }
}, true);

document.addEventListener('focus', function (e) {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.matches('input, select, textarea')) {
        clearFieldError(target);
    }
}, true);

// Initialize improvements
document.addEventListener('DOMContentLoaded', function () {
    // 1. Add error message divs
    document.querySelectorAll('input[required], select[required]').forEach(field => {
        if (!field.nextElementSibling || !field.nextElementSibling.classList.contains('error-message')) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            field.parentNode.insertBefore(errorDiv, field.nextSibling);
        }
    });

    // 2. Add validation on blur
    const ticketInput = document.getElementById('ticket');
    if (ticketInput) {
        ticketInput.addEventListener('blur', function () {
            validateTicket(this);
        });
        // Force numeric keyboard
        ticketInput.setAttribute('inputmode', 'numeric');
        ticketInput.setAttribute('pattern', '[0-9]{11}');
    }

    // 3. Format evaluation fields on blur
    document.addEventListener('blur', function (e) {
        if (e.target.classList.contains('eval')) {
            formatEvaluation(e.target);
        }
    }, true);

    // 4. Handle sticky footer padding
    const stickyFooter = document.querySelector('.sticky-footer');
    if (stickyFooter) {
        // Add padding to body to prevent content being hidden
        document.body.style.paddingBottom = '100px';
    }

    // 5. Auto-fill department from localStorage
    const deptInput = document.getElementById('department');
    if (deptInput) {
        const lastDept = localStorage.getItem('last_department');
        if (lastDept && !deptInput.value) {
            deptInput.value = lastDept;
        }

        // Save on change
        deptInput.addEventListener('change', function () {
            localStorage.setItem('last_department', this.value);
        });
    }
});
