"""Chimera-specific exception classes."""

from __future__ import annotations


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
mutants_xǁBudgetExhaustedErrorǁ__init____mutmut: MutantDict = {}  # type: ignore


class BudgetExhaustedError(Exception):
    """Raised when a provider returns a quota/budget exhaustion error.

    This indicates the account has hit its spending limit, run out of
    credits, or has a billing issue that prevents further API calls.
    """

    @_mutmut_mutated(mutants_xǁBudgetExhaustedErrorǁ__init____mutmut)
    def __init__(self, model: str, provider: str, details: str = "") -> None:
        self.model = model
        self.provider = provider
        self.details = details
        msg = f"Budget exhausted for model '{model}' (provider: {provider})"
        if details:
            msg = f"{msg}: {details}"
        super().__init__(msg)

    def xǁBudgetExhaustedErrorǁ__init____mutmut_orig(self, model: str, provider: str, details: str = "") -> None:
        self.model = model
        self.provider = provider
        self.details = details
        msg = f"Budget exhausted for model '{model}' (provider: {provider})"
        if details:
            msg = f"{msg}: {details}"
        super().__init__(msg)

    def xǁBudgetExhaustedErrorǁ__init____mutmut_1(self, model: str, provider: str, details: str = "XXXX") -> None:
        self.model = model
        self.provider = provider
        self.details = details
        msg = f"Budget exhausted for model '{model}' (provider: {provider})"
        if details:
            msg = f"{msg}: {details}"
        super().__init__(msg)

    def xǁBudgetExhaustedErrorǁ__init____mutmut_2(self, model: str, provider: str, details: str = "") -> None:
        self.model = None
        self.provider = provider
        self.details = details
        msg = f"Budget exhausted for model '{model}' (provider: {provider})"
        if details:
            msg = f"{msg}: {details}"
        super().__init__(msg)

    def xǁBudgetExhaustedErrorǁ__init____mutmut_3(self, model: str, provider: str, details: str = "") -> None:
        self.model = model
        self.provider = None
        self.details = details
        msg = f"Budget exhausted for model '{model}' (provider: {provider})"
        if details:
            msg = f"{msg}: {details}"
        super().__init__(msg)

    def xǁBudgetExhaustedErrorǁ__init____mutmut_4(self, model: str, provider: str, details: str = "") -> None:
        self.model = model
        self.provider = provider
        self.details = None
        msg = f"Budget exhausted for model '{model}' (provider: {provider})"
        if details:
            msg = f"{msg}: {details}"
        super().__init__(msg)

    def xǁBudgetExhaustedErrorǁ__init____mutmut_5(self, model: str, provider: str, details: str = "") -> None:
        self.model = model
        self.provider = provider
        self.details = details
        msg = None
        if details:
            msg = f"{msg}: {details}"
        super().__init__(msg)

    def xǁBudgetExhaustedErrorǁ__init____mutmut_6(self, model: str, provider: str, details: str = "") -> None:
        self.model = model
        self.provider = provider
        self.details = details
        msg = f"Budget exhausted for model '{model}' (provider: {provider})"
        if details:
            msg = None
        super().__init__(msg)

    def xǁBudgetExhaustedErrorǁ__init____mutmut_7(self, model: str, provider: str, details: str = "") -> None:
        self.model = model
        self.provider = provider
        self.details = details
        msg = f"Budget exhausted for model '{model}' (provider: {provider})"
        if details:
            msg = f"{msg}: {details}"
        super().__init__(None)

mutants_xǁBudgetExhaustedErrorǁ__init____mutmut['_mutmut_orig'] = BudgetExhaustedError.xǁBudgetExhaustedErrorǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁBudgetExhaustedErrorǁ__init____mutmut['xǁBudgetExhaustedErrorǁ__init____mutmut_1'] = BudgetExhaustedError.xǁBudgetExhaustedErrorǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁBudgetExhaustedErrorǁ__init____mutmut['xǁBudgetExhaustedErrorǁ__init____mutmut_2'] = BudgetExhaustedError.xǁBudgetExhaustedErrorǁ__init____mutmut_2 # type: ignore # mutmut generated
mutants_xǁBudgetExhaustedErrorǁ__init____mutmut['xǁBudgetExhaustedErrorǁ__init____mutmut_3'] = BudgetExhaustedError.xǁBudgetExhaustedErrorǁ__init____mutmut_3 # type: ignore # mutmut generated
mutants_xǁBudgetExhaustedErrorǁ__init____mutmut['xǁBudgetExhaustedErrorǁ__init____mutmut_4'] = BudgetExhaustedError.xǁBudgetExhaustedErrorǁ__init____mutmut_4 # type: ignore # mutmut generated
mutants_xǁBudgetExhaustedErrorǁ__init____mutmut['xǁBudgetExhaustedErrorǁ__init____mutmut_5'] = BudgetExhaustedError.xǁBudgetExhaustedErrorǁ__init____mutmut_5 # type: ignore # mutmut generated
mutants_xǁBudgetExhaustedErrorǁ__init____mutmut['xǁBudgetExhaustedErrorǁ__init____mutmut_6'] = BudgetExhaustedError.xǁBudgetExhaustedErrorǁ__init____mutmut_6 # type: ignore # mutmut generated
mutants_xǁBudgetExhaustedErrorǁ__init____mutmut['xǁBudgetExhaustedErrorǁ__init____mutmut_7'] = BudgetExhaustedError.xǁBudgetExhaustedErrorǁ__init____mutmut_7 # type: ignore # mutmut generated


__all__ = ["BudgetExhaustedError"]
