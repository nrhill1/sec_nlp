// src/filings/metadata.rs - Filing metadata and helpers
use super::SecFormType;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
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
pub enum FilingFrequency {
    Annual,
    Quarterly,
    SemiAnnual,
    EventDriven,
    Ongoing,
    AsNeeded,
}

impl SecFormType {
    /// Returns true if this is an amended filing (ends with /A)
    pub fn is_amendment(&self) -> bool {
        matches!(
            self,
            SecFormType::TenKA
                | SecFormType::TenQA
                | SecFormType::EightKA
                | SecFormType::S1A
                | SecFormType::S3A
                | SecFormType::S4A
                | SecFormType::S8A
                | SecFormType::S11A
                | SecFormType::SB1A
                | SecFormType::SB2A
                | SecFormType::TwentyFA
                | SecFormType::SixKA
                | SecFormType::ElevenKA
                | SecFormType::FortyFA
                | SecFormType::FortyFR12BA
                | SecFormType::FortyFR12GA
                | SecFormType::ThirteenFHrA
                | SecFormType::ThirteenFNTA
                | SecFormType::Sc13DA
                | SecFormType::Sc13GA
                | SecFormType::Form3A
                | SecFormType::Form4A
                | SecFormType::Form5A
                | SecFormType::F1A
                | SecFormType::OneFortyFourA
                | SecFormType::DefM14AA
                | SecFormType::DefC14AA
                | SecFormType::DefC14CA
                | SecFormType::NT10KA
                | SecFormType::NT10QA
                | SecFormType::TwentyFiveA
        )
    }

    /// Returns the base form type (strips /A amendment suffix)
    pub fn base_type(&self) -> Self {
        match self {
            SecFormType::TenKA => SecFormType::TenK,
            SecFormType::TenQA => SecFormType::TenQ,
            SecFormType::EightKA => SecFormType::EightK,
            SecFormType::S1A => SecFormType::S1,
            SecFormType::S3A => SecFormType::S3,
            SecFormType::S4A => SecFormType::S4,
            SecFormType::S8A => SecFormType::S8,
            SecFormType::S11A => SecFormType::S11,
            SecFormType::SB1A => SecFormType::SB1,
            SecFormType::SB2A => SecFormType::SB2,
            SecFormType::TwentyFA => SecFormType::TwentyF,
            SecFormType::SixKA => SecFormType::SixK,
            SecFormType::ElevenKA => SecFormType::ElevenK,
            SecFormType::FortyFA => SecFormType::FortyF,
            SecFormType::FortyFR12BA => SecFormType::FortyFR12B,
            SecFormType::FortyFR12GA => SecFormType::FortyFR12G,
            SecFormType::ThirteenFHrA => SecFormType::ThirteenFHr,
            SecFormType::ThirteenFNTA => SecFormType::ThirteenFNT,
            SecFormType::Sc13DA => SecFormType::Sc13D,
            SecFormType::Sc13GA => SecFormType::Sc13G,
            SecFormType::Form3A => SecFormType::Form3,
            SecFormType::Form4A => SecFormType::Form4,
            SecFormType::Form5A => SecFormType::Form5,
            SecFormType::F1A => SecFormType::F1,
            SecFormType::OneFortyFourA => SecFormType::OneFortyFour,
            SecFormType::DefM14AA => SecFormType::DefM14A,
            SecFormType::DefC14AA => SecFormType::DefC14A,
            SecFormType::DefC14CA => SecFormType::DefC14C,
            SecFormType::NT10KA => SecFormType::NT10K,
            SecFormType::NT10QA => SecFormType::NT10Q,
            SecFormType::TwentyFiveA => SecFormType::TwentyFive,
            other => *other,
        }
    }

    /// Returns the filing category
    pub fn category(&self) -> FilingCategory {
        match self.base_type() {
            SecFormType::TenK | SecFormType::TenQ | SecFormType::TwentyF => {
                FilingCategory::PeriodicReport
            }
            SecFormType::EightK | SecFormType::SixK => FilingCategory::CurrentReport,
            SecFormType::Def14A
            | SecFormType::Def14C
            | SecFormType::DefM14A
            | SecFormType::DefC14A
            | SecFormType::DefC14C => FilingCategory::ProxyStatement,
            SecFormType::S1
            | SecFormType::S3
            | SecFormType::S4
            | SecFormType::S8
            | SecFormType::S11
            | SecFormType::SB1
            | SecFormType::SB2
            | SecFormType::F1
            | SecFormType::F3
            | SecFormType::F4
            | SecFormType::F6 => FilingCategory::Registration,
            SecFormType::Sc13D | SecFormType::Sc13G => FilingCategory::BeneficialOwnership,
            SecFormType::Form3 | SecFormType::Form4 | SecFormType::Form5 => {
                FilingCategory::InsiderTrading
            }
            SecFormType::ThirteenFHr | SecFormType::ThirteenFNT => {
                FilingCategory::InstitutionalHoldings
            }
            SecFormType::FortyF | SecFormType::FortyFR12B | SecFormType::FortyFR12G => {
                FilingCategory::ForeignIssuer
            }
            SecFormType::FourTwoFourB5
            | SecFormType::FourTwoFive
            | SecFormType::PosEx
            | SecFormType::Pos462B
            | SecFormType::Pos462C
            | SecFormType::PosAsr
            | SecFormType::OneFortyFour
            | SecFormType::FormD => FilingCategory::Offering,
            SecFormType::NT10K | SecFormType::NT10Q | SecFormType::NT11K | SecFormType::NT15D2 => {
                FilingCategory::Notification
            }
            _ => FilingCategory::Other,
        }
    }

    /// Returns typical filing frequency
    pub fn frequency(&self) -> FilingFrequency {
        match self.base_type() {
            SecFormType::TenK | SecFormType::TwentyF | SecFormType::ElevenK => {
                FilingFrequency::Annual
            }
            SecFormType::TenQ => FilingFrequency::Quarterly,
            SecFormType::SixK => FilingFrequency::SemiAnnual,
            SecFormType::EightK | SecFormType::Form4 => FilingFrequency::EventDriven,
            SecFormType::Form3 | SecFormType::Form5 => FilingFrequency::AsNeeded,
            SecFormType::ThirteenFHr => FilingFrequency::Quarterly,
            _ => FilingFrequency::AsNeeded,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_amendment() {
        assert!(SecFormType::TenKA.is_amendment());
        assert!(!SecFormType::TenK.is_amendment());
        assert!(SecFormType::EightKA.is_amendment());
    }

    #[test]
    fn test_base_type() {
        assert_eq!(SecFormType::TenKA.base_type(), SecFormType::TenK);
        assert_eq!(SecFormType::TenK.base_type(), SecFormType::TenK);
        assert_eq!(SecFormType::S1A.base_type(), SecFormType::S1);
    }

    #[test]
    fn test_category() {
        assert_eq!(SecFormType::TenK.category(), FilingCategory::PeriodicReport);
        assert_eq!(
            SecFormType::EightK.category(),
            FilingCategory::CurrentReport
        );
        assert_eq!(
            SecFormType::Form4.category(),
            FilingCategory::InsiderTrading
        );
    }

    #[test]
    fn test_frequency() {
        assert_eq!(SecFormType::TenK.frequency(), FilingFrequency::Annual);
        assert_eq!(SecFormType::TenQ.frequency(), FilingFrequency::Quarterly);
        assert_eq!(
            SecFormType::EightK.frequency(),
            FilingFrequency::EventDriven
        );
    }
}
