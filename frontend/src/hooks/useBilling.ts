import { useCallback, useEffect, useRef, useState } from 'react';
import {
  cancelSubscription,
  changePlan,
  getInvoices,
  getPaymentMethod,
  getSubscription,
  getUsageMetrics,
} from '../services/billingApi';
import type { BillingInterval, Invoice, PaymentMethod, Subscription, UsageMetrics } from '../types/settingsTypes';

export function useBilling() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | null>(null);
  const [usage, setUsage] = useState<UsageMetrics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isMountedRef = useRef(true);

  useEffect(() => () => {
    isMountedRef.current = false;
  }, []);

  const refetch = useCallback(async () => {
    try {
      if (isMountedRef.current) {
        setIsLoading(true);
        setError(null);
      }
      const [subData, invoiceData, paymentData, usageData] = await Promise.all([
        getSubscription(),
        getInvoices(),
        getPaymentMethod(),
        getUsageMetrics(),
      ]);
      if (isMountedRef.current) {
        setSubscription(subData);
        setInvoices(invoiceData);
        setPaymentMethod(paymentData);
        setUsage(usageData);
      }
    } catch (err) {
      if (isMountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to load billing data');
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { subscription, invoices, paymentMethod, usage, isLoading, error, refetch };
}

export function useChangePlan() {
  return useCallback((planId: string, interval: BillingInterval) => changePlan(planId, interval), []);
}

export function useCancelSubscription() {
  return useCallback(() => cancelSubscription(), []);
}
