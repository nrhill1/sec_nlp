
//! Module-level metadata and helper utilities for EDGAR filing types.
//!
//! This module provides:
//!
//! - `FilingCategory`: an enum classifying filings into high-level categories
//!   (e.g., PeriodicReport, CurrentReport, ProxyStatement, Registration, etc.).
//! - `FilingFrequency`: an enum describing the typical cadence a filing is
//!   expected to follow (e.g., Annual, Quarterly, EventDriven, AsNeeded).
//! - Helper methods implemented on `FormType` to inspect and normalize form
//!   kinds:
//!     - `is_amendment(&self) -> bool` — returns true for amended variants
//!       (those representing a base form with an "/A" amendment suffix).
//!     - `base_type(&self) -> Self` — returns the non-amended/base variant for a
//!       given form (amendments are mapped back to their base form).
//!     - `category(&self) -> FilingCategory` — classifies the form (using the
//!       base type) into a `FilingCategory`. Unknown or uncategorized forms
//!       return `FilingCategory::Other`.
//!     - `frequency(&self) -> FilingFrequency` — returns a typical filing
//!       frequency for the base form. When no typical cadence is defined the
//!       method defaults to `FilingFrequency::AsNeeded`.
//!
//! Notes and behavior:
//! - The classification and frequency decisions are based on the canonical
//!   (non-amended) form type returned by `base_type()`; calling these helpers
//!   on amended variants will yield results appropriate to the underlying base
//!   form.
//! - The enums derive `Debug`, `Clone`, `Copy`, `PartialEq`, and `Eq` for easy
//!   use in matching, comparisons and logging.
//!
//! Example (informal):
//! - `FormType::TenKA.is_amendment()` -> true
//! - `FormType::TenKA.base_type()` -> `FormType::TenK`
//! - `FormType::TenK.category()` -> `FilingCategory::PeriodicReport`
//! - `FormType::EightK.frequency()` -> `FilingFrequency::EventDriven`
//!
//! This module is intended to centralize filing-related metadata used across
//! the crate so that categorization and frequency logic is kept consistent and
//! easy to test.

use super::FormType;

// TODO: Write docs for enum vars
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(missing_docs)]
pub enum FilingCategory {
    PeriodicReport,
    CurrentReport,
    ProxyStatement,
    Registration,
    BeneficialOwnership,
    InsiderTrading,
    InstitutionalHoldings,
    ForeignIssuer,
    Offering,
    Notification,
    Other,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(missing_docs)]
pub enum FilingFrequency {
    Annual,
    Quarterly,
    SemiAnnual,
    EventDriven,
    Ongoing,
    AsNeeded,
}

impl FormType {
    /// Returns true if this is an amended filing (ends with /A)
    pub fn is_amendment(&self) -> bool {
        matches!(
            self,
            FormType::TenKA
                | FormType::TenQA
                | FormType::EightKA
                | FormType::S1A
                | FormType::S3A
                | FormType::S4A
                | FormType::S8A
                | FormType::S11A
                | FormType::SB1A
                | FormType::SB2A
                | FormType::TwentyFA
                | FormType::SixKA
                | FormType::ElevenKA
                | FormType::FortyFA
                | FormType::FortyFR12BA
                | FormType::FortyFR12GA
                | FormType::ThirteenFHrA
                | FormType::ThirteenFNTA
                | FormType::Sc13DA
                | FormType::Sc13GA
                | FormType::Form3A
                | FormType::Form4A
                | FormType::Form5A
                | FormType::F1A
                | FormType::OneFortyFourA
                | FormType::DefM14AA
                | FormType::DefC14AA
                | FormType::DefC14CA
                | FormType::NT10KA
                | FormType::NT10QA
                | FormType::TwentyFiveA
        )
    }

    /// Returns the base form type (strips /A amendment suffix)
    pub fn base_type(&self) -> Self {
        match self {
            FormType::TenKA => FormType::TenK,
            FormType::TenQA => FormType::TenQ,
            FormType::EightKA => FormType::EightK,
            FormType::S1A => FormType::S1,
            FormType::S3A => FormType::S3,
            FormType::S4A => FormType::S4,
            FormType::S8A => FormType::S8,
            FormType::S11A => FormType::S11,
            FormType::SB1A => FormType::SB1,
            FormType::SB2A => FormType::SB2,
            FormType::TwentyFA => FormType::TwentyF,
            FormType::SixKA => FormType::SixK,
            FormType::ElevenKA => FormType::ElevenK,
            FormType::FortyFA => FormType::FortyF,
            FormType::FortyFR12BA => FormType::FortyFR12B,
            FormType::FortyFR12GA => FormType::FortyFR12G,
            FormType::ThirteenFHrA => FormType::ThirteenFHr,
            FormType::ThirteenFNTA => FormType::ThirteenFNT,
            FormType::Sc13DA => FormType::Sc13D,
            FormType::Sc13GA => FormType::Sc13G,
            FormType::Form3A => FormType::Form3,
            FormType::Form4A => FormType::Form4,
            FormType::Form5A => FormType::Form5,
            FormType::F1A => FormType::F1,
            FormType::OneFortyFourA => FormType::OneFortyFour,
            FormType::DefM14AA => FormType::DefM14A,
            FormType::DefC14AA => FormType::DefC14A,
            FormType::DefC14CA => FormType::DefC14C,
            FormType::NT10KA => FormType::NT10K,
            FormType::NT10QA => FormType::NT10Q,
            FormType::TwentyFiveA => FormType::TwentyFive,
            other => *other,
        }
    }

    /// Returns the filing category
    pub fn category(&self) -> FilingCategory {
        match self.base_type() {
            FormType::TenK | FormType::TenQ | FormType::TwentyF => FilingCategory::PeriodicReport,
            FormType::EightK | FormType::SixK => FilingCategory::CurrentReport,
            FormType::Def14A | FormType::Def14C | FormType::DefM14A | FormType::DefC14A | FormType::DefC14C => {
                FilingCategory::ProxyStatement
            }
            FormType::S1
            | FormType::S3
            | FormType::S4
            | FormType::S8
            | FormType::S11
            | FormType::SB1
            | FormType::SB2
            | FormType::F1
            | FormType::F3
            | FormType::F4
            | FormType::F6 => FilingCategory::Registration,
            FormType::Sc13D | FormType::Sc13G => FilingCategory::BeneficialOwnership,
            FormType::Form3 | FormType::Form4 | FormType::Form5 => FilingCategory::InsiderTrading,
            FormType::ThirteenFHr | FormType::ThirteenFNT => FilingCategory::InstitutionalHoldings,
            FormType::FortyF | FormType::FortyFR12B | FormType::FortyFR12G => FilingCategory::ForeignIssuer,
            FormType::FourTwoFourB5
            | FormType::FourTwoFive
            | FormType::PosEx
            | FormType::Pos462B
            | FormType::Pos462C
            | FormType::PosAsr
            | FormType::OneFortyFour
            | FormType::FormD => FilingCategory::Offering,
            FormType::NT10K | FormType::NT10Q | FormType::NT11K | FormType::NT15D2 => FilingCategory::Notification,
            _ => FilingCategory::Other,
        }
    }

    /// Returns typical filing frequency
    pub fn frequency(&self) -> FilingFrequency {
        match self.base_type() {
            FormType::TenK | FormType::TwentyF | FormType::ElevenK => FilingFrequency::Annual,
            FormType::TenQ => FilingFrequency::Quarterly,
            FormType::SixK => FilingFrequency::SemiAnnual,
            FormType::EightK | FormType::Form4 => FilingFrequency::EventDriven,
            FormType::Form3 | FormType::Form5 => FilingFrequency::AsNeeded,
            FormType::ThirteenFHr => FilingFrequency::Quarterly,
            _ => FilingFrequency::AsNeeded,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_amendment() {
        assert!(FormType::TenKA.is_amendment());
        assert!(!FormType::TenK.is_amendment());
        assert!(FormType::EightKA.is_amendment());
    }

    #[test]
    fn test_base_type() {
        assert_eq!(FormType::TenKA.base_type(), FormType::TenK);
        assert_eq!(FormType::TenK.base_type(), FormType::TenK);
        assert_eq!(FormType::S1A.base_type(), FormType::S1);
    }

    #[test]
    fn test_category() {
        assert_eq!(FormType::TenK.category(), FilingCategory::PeriodicReport);
        assert_eq!(FormType::EightK.category(), FilingCategory::CurrentReport);
        assert_eq!(FormType::Form4.category(), FilingCategory::InsiderTrading);
    }

    #[test]
    fn test_frequency() {
        assert_eq!(FormType::TenK.frequency(), FilingFrequency::Annual);
        assert_eq!(FormType::TenQ.frequency(), FilingFrequency::Quarterly);
        assert_eq!(FormType::EightK.frequency(), FilingFrequency::EventDriven);
    }
}
